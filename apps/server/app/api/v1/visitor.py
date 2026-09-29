import json
import re
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ...agent import AgentOrchestrator
from ...config import settings
from ...core.exceptions import AppError
from ...db import get_db
from ...models import HotelService, PartnerResource, ProductAdjustmentRecord, ProductResource, PublicResource, ResourceChangeEvent, RoomInventory, TravelProduct, VisitorIntent
from ...repositories.product_repository import get_product, list_products
from ...schemas.products import ProductRead
from ...schemas.visitor import VisitorIntentCancelRequest, VisitorIntentCreate, VisitorInterpretRequest, VisitorInterpretResponse, VisitorProductQuery, VisitorQuestion, VisitorRecommendRequest
from ...services.inventory_service import reconcile_published_capacity, release_intent_inventory, reserve_product_inventory, sweep_expired_intents
from ...services.media_library_service import MediaLibraryService
from ...services.knowledge_service import KnowledgeService
from ...services.weather_service import WeatherService
from ...services.public_copy import public_travel_copy, visitor_product_to_dict
from ...rules.availability_rule import tokens
from ...rules.crowd_rule import crowd_supported
from ...rules.time_rule import intervals_overlap
from ...rules.weather_rule import is_weather_supported
from ..websocket_manager import manager

router = APIRouter(prefix="/visitor", tags=["visitor"])


@router.get("/media/cover")
def public_cover_image(query: str = Query(min_length=2, max_length=180)):
    """Resolve a different licensed cover on demand when a resource has no upload."""
    try:
        media = MediaLibraryService().automatic_cover(query)
    except AppError:
        return Response(status_code=204)
    # Browsers request the stable query URL on every card render.  Cache the
    # redirect as well as the server-owned file so a known resource never has
    # to repeat the Commons lookup before its image appears.
    response = RedirectResponse(media["image_url"], status_code=302)
    response.headers["Cache-Control"] = "public, max-age=86400, stale-while-revalidate=604800"
    return response


@router.get("/media/proxy")
def public_media_proxy(url: str = Query(min_length=10, max_length=600)):
    """Serve a known public image from local storage.

    Storefront cards point at curated public images; copying each one once and
    redirecting keeps repeat views instant instead of re-downloading from a
    third-party host on every render.
    """

    try:
        media = MediaLibraryService().proxy_remote(url)
    except AppError:
        # Never turn an untrusted URL into an open redirect. The caller can
        # render its own placeholder when a public image cannot be cached.
        return Response(status_code=204)
    response = RedirectResponse(media["image_url"], status_code=302)
    response.headers["Cache-Control"] = "public, max-age=604800, immutable"
    return response


CN_NUMBERS = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

PREFERENCE_ALIASES: dict[str, tuple[str, ...]] = {
    "THEME_PARK": ("乐园", "主题公园", "游乐园", "theme park"),
    "KIDS": ("儿童乐园", "儿童探索", "kids"),
    "CULTURE": ("非遗", "手作", "手工", "文化", "博物馆", "museum"),
    "TEA": ("茶", "点茶", "茶文化", "tea"),
    "SPORT": ("运动", "攀岩", "卡丁车", "射箭", "刺激", "sport"),
    "NIGHTLIFE": ("夜游", "夜景", "音乐现场", "夜生活", "nightlife"),
    "PHOTO": ("旅拍", "摄影", "拍照", "photo"),
    "FOOD": ("美食", "杭帮菜", "甜品", "咖啡", "烘焙", "food"),
    "NATURE": ("自然", "湿地", "动物", "植物", "nature"),
    "PERFORMANCE": ("演出", "儿童剧", "剧场", "performance"),
    "CITY_WALK": ("漫游", "散步", "骑行", "街巷", "city walk"),
    "SLOW": ("慢游", "慢慢", "轻松", "休息", "安静", "放松", "slow"),
}
NEGATIVE_MARKERS = ("不想", "不要", "不喜欢", "不爱", "避开", "别安排", "不考虑")

# Hangzhou districts/areas used to keep recommendations near each other: a
# museum request next to a canal product should prefer canal-side museums.
AREA_KEYWORDS = (
    "西湖", "湖滨", "运河", "拱宸桥", "小河直街", "良渚", "西溪", "湘湖", "龙井",
    "灵隐", "钱江新城", "钱塘江", "南山路", "河坊街", "清河坊", "滨江", "城西",
    "城北", "上城区", "西湖区", "余杭", "萧山", "桥西", "武林", "湖墅",
)


def area_tokens(*values: object) -> set[str]:
    text = " ".join(str(value or "") for value in values)
    return {keyword for keyword in AREA_KEYWORDS if keyword in text}

PREFERENCE_LABELS = {
    "THEME_PARK": "主题乐园",
    "KIDS": "儿童体验",
    "CULTURE": "文化展馆",
    "TEA": "茶文化",
    "SPORT": "运动",
    "NIGHTLIFE": "夜游",
    "PHOTO": "旅拍",
    "FOOD": "美食",
    "NATURE": "自然",
    "PERFORMANCE": "演出",
    "CITY_WALK": "城市漫游",
    "SLOW": "轻松慢游",
}


def display_preference_terms(terms: list[object]) -> list[str]:
    result: list[str] = []
    for term in terms:
        value = str(term)
        label = PREFERENCE_LABELS.get(value.upper(), value)
        if label and label not in result:
            result.append(label)
    return result


def preference_categories(text: str) -> set[str]:
    lowered = text.lower()
    return {category for category, aliases in PREFERENCE_ALIASES.items() if any(alias.lower() in lowered for alias in aliases)}


def negative_preference_categories(text: str) -> set[str]:
    lowered = text.lower()
    found: set[str] = set()
    for category, aliases in PREFERENCE_ALIASES.items():
        for alias in aliases:
            if any(re.search(rf"{re.escape(marker.lower())}.{{0,4}}{re.escape(alias.lower())}", lowered) for marker in NEGATIVE_MARKERS):
                found.add(category)
                break
    if any(phrase in lowered for phrase in ("不想走太多路", "少走路", "不想徒步", "不想太累")):
        found.update({"CITY_WALK", "NATURE", "SPORT"})
    return found


def number_value(value: str, default: int = 0) -> int:
    return int(value) if value.isdigit() else CN_NUMBERS.get(value, default)


def parse_clock(prefix: str | None, value: str, default: int = 15) -> time:
    hour = number_value(value, default)
    if prefix and prefix in {"下午", "晚上"} and hour < 12:
        hour += 12
    return time(min(hour, 23), 0)


def interpreted_needs(request: VisitorRecommendRequest, text: str | None = None) -> dict[str, object]:
    """Serialize the exact deterministic request used by matching."""
    return {
        "natural_language": text if text is not None else request.natural_language.strip(),
        "target_date": request.target_date.isoformat() if request.target_date else None,
        "weather": request.weather,
        "target_crowd": request.target_crowd,
        "budget": str(request.budget),
        "adult_count": request.adult_count,
        "child_count": request.child_count,
        "child_ages": request.child_ages,
        "interests": request.interests,
        "negative_interests": request.negative_interests,
        "activity_level": request.activity_level,
        "requested_places": request.requested_places,
        "dietary_restrictions": request.dietary_restrictions,
        "allergy_information": request.allergy_information,
        "arrival_time": request.arrival_time.strftime("%H:%M") if request.arrival_time else None,
        "preferred_experience_time": request.preferred_experience_time.strftime("%H:%M") if request.preferred_experience_time else None,
        "other_requirements": request.other_requirements or (text or request.natural_language.strip()),
    }


def parse_weekday(text: str) -> date | None:
    if "周末" in text:
        days = (5 - date.today().weekday()) % 7 or 7
        return date.today() + timedelta(days=days)
    match = re.search(r"(?:周|星期)([一二三四五六日天])", text)
    if not match:
        return None
    index = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}[match.group(1)]
    days = (index - date.today().weekday()) % 7 or 7
    return date.today() + timedelta(days=days)


def enrich_recommend_request(request: VisitorRecommendRequest) -> tuple[VisitorRecommendRequest, dict[str, object]]:
    """Turn visitor free text into structured hints before deterministic matching.

    The parser is deliberately small and explainable. The Agent can phrase the
    recommendation, but budget, weather, age and inventory decisions continue to
    use this structured request and the database rules.
    """
    text = request.natural_language.strip()
    if not text:
        return request, {}
    updates: dict[str, object] = {}
    categories = preference_categories(text)
    negative_categories = negative_preference_categories(text)
    if any(word in text for word in ("情侣", "夫妻", "约会", "两个人", "两人")) and not any(word in text for word in ("孩子", "儿童", "小孩", "小朋友", "岁")):
        updates["target_crowd"] = "COUPLE"
    elif any(word in text for word in ("朋友", "同学", "室友", "大学生", "兄弟", "闺蜜")):
        updates["target_crowd"] = "FRIENDS"
    elif any(word in text for word in ("一个人", "独自", "solo", "自己旅行")):
        updates["target_crowd"] = "SOLO"
    elif any(word in text for word in ("本地", "周末微度假", "周末放松")):
        updates["target_crowd"] = "LOCAL_WEEKEND"
    activity_level = "HIGH" if any(word in text for word in ("刺激", "挑战", "运动", "攀岩", "卡丁车")) else "LOW" if any(word in text for word in ("不想走太多路", "少走路", "轻松", "休息", "慢一点")) else None
    if activity_level:
        updates["activity_level"] = activity_level
    # A date selected in the UI is explicit and must win over casual wording
    # such as “tomorrow” in the free-text note.  Only infer a date when none
    # was supplied by the visitor.
    if request.target_date is None:
        if "明天" in text:
            updates["target_date"] = date.today() + timedelta(days=1)
        elif "今天" in text:
            updates["target_date"] = date.today()
        else:
            weekday = parse_weekday(text)
            if weekday:
                updates["target_date"] = weekday
    weather = "RAIN" if any(word in text for word in ("雨", "下雨", "湿冷")) else "SUNNY" if "晴" in text else "CLOUDY" if any(word in text for word in ("多云", "阴天")) else None
    if weather:
        updates["weather"] = weather
    budget_match = re.search(r"(?:预算|花费|控制在|不超过|以内)[^0-9]{0,8}(\d{3,5})", text)
    if budget_match:
        updates["budget"] = Decimal(budget_match.group(1))
    ages = [int(value) for value in re.findall(r"(\d{1,2})\s*岁", text)]
    if ages:
        updates["child_ages"] = ages
        updates["child_count"] = len(ages)
    group_match = re.search(r"([一二两三四五六七八九十\d]+)\s*大\s*([一二两三四五六七八九十\d]+)\s*小", text)
    if group_match:
        updates["adult_count"] = number_value(group_match.group(1), request.adult_count)
        updates["child_count"] = number_value(group_match.group(2), request.child_count)
    adult_match = re.search(r"(\d+|[一二两三四五六七八九十])\s*(?:位)?大人", text)
    if adult_match:
        value = adult_match.group(1)
        updates["adult_count"] = number_value(value, request.adult_count)
    family_match = re.search(r"一家([一二两三四五六七八九十\d]+)口", text)
    if family_match and "adult_count" not in updates:
        total = number_value(family_match.group(1), request.adult_count + request.child_count)
        # A family phrase is not a reason to fall back to the UI defaults. If
        # ages are supplied, they define the child count; otherwise use the
        # common two-adult family split and leave editable age slots visible.
        inferred_children = len(ages) if ages else max(total - min(2, max(total - 1, 1)), 0)
        updates["adult_count"] = max(total - inferred_children, 1)
        updates["child_count"] = inferred_children
    friends_match = re.search(r"([一二两三四五六七八九十\d]+)\s*(?:个|位)?朋友", text)
    if friends_match and "adult_count" not in updates:
        updates["adult_count"] = number_value(friends_match.group(1), request.adult_count)
        updates["child_count"] = 0
        updates["child_ages"] = []
    couple_match = re.search(r"情侣\s*([一二两三四五六七八九十\d]+)?\s*(?:个人|人)?", text)
    if couple_match and "adult_count" not in updates:
        updates["adult_count"] = number_value(couple_match.group(1) or "两", 2)
        updates["child_count"] = 0
        updates["child_ages"] = []
    child_count_match = re.search(r"(\d+|[一二两三四五六七八九十])\s*(?:位)?(?:个)?(?:小孩|儿童|孩子|小朋友)", text)
    if child_count_match and "child_count" not in updates:
        value = child_count_match.group(1)
        updates["child_count"] = number_value(value, request.child_count)
    if any(word in text for word in ("情侣", "夫妻", "两个人", "两人")) and not any(word in text for word in ("孩子", "儿童", "小孩", "小朋友", "岁")):
        updates["child_count"] = 0
        updates["child_ages"] = []
    interests = [word for word in ("亲子", "手工", "非遗", "茶", "点茶", "博物馆", "摄影", "旅拍", "美食", "慢游", "乐园", "运动", "夜游", "演出", "自然", "咖啡") if word in text]
    interests.extend(sorted(categories - negative_categories))
    if interests:
        updates["interests"] = list(dict.fromkeys([*request.interests, *interests]))
    if negative_categories:
        updates["negative_interests"] = list(dict.fromkeys([*request.negative_interests, *sorted(negative_categories)]))
    dietary_terms = [word for word in ("不吃辣", "素食", "清真", "不吃海鲜", "不吃牛肉") if word in text]
    allergy_terms = [word for word in ("花生", "坚果", "牛奶", "乳制品", "海鲜", "鸡蛋") if word in text and ("过敏" in text or "忌" in text)]
    if dietary_terms or allergy_terms:
        updates["dietary_restrictions"] = list(dict.fromkeys([*request.dietary_restrictions, *dietary_terms, *allergy_terms]))
    if allergy_terms:
        updates["allergy_information"] = request.allergy_information or "、".join(f"{item}过敏" for item in allergy_terms)
    places = [word for word in ("西湖", "运河", "拱宸桥", "茶园", "博物馆", "宋城", "灵隐寺") if word in text]
    if places:
        updates["requested_places"] = list(dict.fromkeys([*request.requested_places, *places]))
    arrival_match = re.search(r"(?:到店|抵达|入住|到达|到杭州)[^，。；,;]{0,10}?(上午|下午|晚上|早上)?\s*([一二两三四五六七八九十\d]{1,2})\s*点", text)
    if not arrival_match:
        arrival_match = re.search(r"(上午|下午|晚上|早上)?\s*([一二两三四五六七八九十\d]{1,2})\s*点[^，。；,;]{0,6}?(?:到店|抵达|入住|到达|到杭州)", text)
    preferred_match = re.search(r"(?:(?:体验|活动|场次|玩|出发)[^，。；,;]{0,8}?(上午|下午|晚上|早上)?\s*([一二两三四五六七八九十\d]{1,2})\s*点|(上午|下午|晚上|早上)?\s*([一二两三四五六七八九十\d]{1,2})\s*点[^，。；,;]{0,4}?(?:体验|活动|场次|玩))", text)
    generic_match = re.search(r"(上午|下午|晚上|早上)?\s*([一二两三四五六七八九十\d]{1,2})\s*点", text)
    if arrival_match and request.arrival_time is None:
        updates["arrival_time"] = parse_clock(arrival_match.group(1), arrival_match.group(2))
    elif generic_match and request.arrival_time is None and not preferred_match:
        updates["arrival_time"] = parse_clock(generic_match.group(1), generic_match.group(2))
    if preferred_match and request.preferred_experience_time is None:
        prefix, value = (preferred_match.group(1), preferred_match.group(2)) if preferred_match.group(2) else (preferred_match.group(3), preferred_match.group(4))
        updates["preferred_experience_time"] = parse_clock(prefix, value)
    effective = request.model_copy(update=updates)
    interpreted = interpreted_needs(effective, text)
    return effective, interpreted


def follow_up_questions(request: VisitorRecommendRequest, interpreted: dict[str, object]) -> list[str]:
    questions: list[str] = []
    if not request.target_date:
        questions.append("想安排哪天入住？不填也可以先看当前可售套餐。")
    if request.child_count and not request.child_ages:
        questions.append("如果同行有儿童，方便补充每位儿童年龄吗？系统会据此校验体验安全范围。")
    if not request.budget:
        questions.append("这次预算上限大约是多少？")
    if not request.requested_places and not request.interests:
        questions.append("更想去哪里或体验什么？例如西湖、运河、非遗、茶文化。")
    return questions[:3]


def is_publicly_sellable(product: TravelProduct, *, today: date | None = None) -> bool:
    """A visitor can only see products whose departure date has not passed."""
    current = today or date.today()
    return product.target_date is not None and product.target_date >= current and product.status in {"ON_SALE", "LOW_STOCK"}


def public_items(
    db: Session,
    query: VisitorProductQuery | None = None,
    *,
    limit: int = 30,
    offset: int = 0,
) -> list[TravelProduct]:
    # The unfiltered landing page is paged in SQL.  Filtered/interest searches
    # still load the bounded public set so ranking is correct, then page the
    # ranked result below instead of applying a limit before matching.
    needs_matching = bool(query and (query.target_date or query.budget or query.target_crowd or query.interest))
    source = list_products(db, public_only=True) if needs_matching else list_products(db, public_only=True, limit=limit, offset=offset)
    products = [item for item in source if is_publicly_sellable(item)]
    if query and query.target_date:
        products = [item for item in products if item.target_date == query.target_date]
    if query and query.budget:
        products = [item for item in products if item.suggested_price <= query.budget]
    if query and query.target_crowd:
        products = [item for item in products if item.target_crowd == query.target_crowd or item.target_crowd == "ALL"]
    if query and query.interest:
        needle = query.interest.strip().lower()
        if needle:
            # Rank on the product title, theme and its real resources.  The
            # generated day-by-day copy is excluded: it mentions every nearby
            # place, which previously made unrelated products "match".
            terms = [t for t in re.split(r"[\s,，、;；/]+", needle) if len(t) > 1]
            expanded = set(terms)
            for aliases in PREFERENCE_ALIASES.values():
                if any(a.lower() in needle for a in aliases):
                    expanded.update(a.lower() for a in aliases)
            ranked = []
            for item in products:
                title_text = f"{item.product_name} {item.theme}".lower()
                resource_text = " ".join(
                    f"{row.resource_name} {getattr(resource, 'category', '')} {getattr(resource, 'address', '')}".lower()
                    for row, resource in product_partner_rows(db, item)
                )
                service_text = " ".join(
                    str(row.resource_name).lower() for row in item.resources if row.resource_type == "HOTEL_SERVICE"
                )
                score = 0
                for term in expanded:
                    if term in title_text:
                        score += 4
                    elif term in resource_text:
                        score += 3
                    elif term in service_text:
                        score += 1
                if score:
                    ranked.append((score, item))
            ranked.sort(key=lambda pair: (pair[0], pair[1].sale_quantity), reverse=True)
            products = [item for _, item in ranked]
    if needs_matching:
        return products[max(0, offset): max(0, offset) + limit]
    return products


def product_partner_rows(db: Session, product: TravelProduct) -> list[tuple[ProductResource, PartnerResource]]:
    result = []
    for row in product.resources:
        if row.resource_type == "PARTNER_RESOURCE":
            resource = db.get(PartnerResource, row.resource_id)
            if resource:
                result.append((row, resource))
    return result


def _room_pool(db: Session, product: TravelProduct) -> tuple[str, date] | None:
    room = db.get(RoomInventory, product.room_inventory_id)
    if room is None:
        return None
    return str(room.room_type), product.target_date


def shared_room_remaining(db: Session, product: TravelProduct, cache: dict | None = None) -> int:
    """Sellable quantity for one physical room type on one night.

    Every product built on the same room type shares that night's rooms, so a
    room type that is sold out makes all of its packages sold out instead of
    letting each package claim the same rooms again.
    """

    pool_key = _room_pool(db, product)
    if pool_key is None:
        return max(0, int(product.sale_quantity or 0))
    if cache is not None and pool_key in cache:
        return cache[pool_key]
    room_type, target_date = pool_key
    pool = db.scalar(
        select(func.max(RoomInventory.available_count)).where(
            RoomInventory.hotel_id == product.hotel_id,
            RoomInventory.room_type == room_type,
            RoomInventory.available_date == target_date,
        )
    )
    committed = db.scalar(
        select(func.count())
        .select_from(VisitorIntent)
        .join(TravelProduct, VisitorIntent.product_id == TravelProduct.id)
        .join(RoomInventory, RoomInventory.id == TravelProduct.room_inventory_id)
        .where(
            RoomInventory.hotel_id == product.hotel_id,
            RoomInventory.room_type == room_type,
            TravelProduct.target_date == target_date,
            VisitorIntent.reservation_status.in_(("CONFIRMED", "HELD")),
        )
    )
    remaining = max(0, int(pool or 0) - int(committed or 0))
    if cache is not None:
        cache[pool_key] = remaining
    return remaining


def visitor_payload(db: Session, product: TravelProduct, *, nights: int = 1, cache: dict | None = None) -> dict[str, Any]:
    """Serialise a product with the shared room availability applied."""

    data = visitor_product_to_dict(product, nights=nights)
    # Two constraints apply: the product's own listed quota and the room type's
    # shared pool.  The smaller one is what a visitor can actually buy.
    listed = max(0, int(product.listed_quantity or 0))
    remaining = min(max(0, int(product.sale_quantity or 0)), shared_room_remaining(db, product, cache))
    data["sale_quantity"] = remaining
    data["listed_quantity"] = remaining
    # 已经卖出的份数 = 发布份数 - 剩余；用于卡片和详情页显示「已售」。
    data["sold_quantity"] = max(0, listed - remaining)
    if remaining <= 0:
        data["status"] = "SOLD_OUT"
    elif remaining <= 2 and str(data.get("status")) == "ON_SALE":
        data["status"] = "LOW_STOCK"
    return data


def build_detail_sections(db: Session, product: TravelProduct, data: dict[str, Any]) -> dict[str, Any]:
    """Product-specific detail copy: schedule,每项体验, cost, tips.

    Everything is derived from this product's own resources, times, addresses
    and the matching knowledge record, so two packages never read the same.
    """

    resources = data.get("resources") or []
    stay = data.get("stay") or {}
    experiences = [item for item in resources if item.get("resource_type") != "ROOM"]
    days = data.get("day_plan") or []
    room_name = str(stay.get("room_name") or "酒店客房")
    nights = int(stay.get("nights") or 1)

    intro = [
        f"这是一组「{data.get('theme') or data.get('product_name')}」的旅居套餐：{nights} 晚住{room_name}，"
        f"另外包含 {len(experiences)} 项在地体验；每天的时间、集合地点和顺序都会在购买确认里逐条写明。",
    ]
    for day in days:
        slot = day.get("slot_summary") or day.get("summary") or ""
        date_text = f"（{day.get('date')}）" if day.get("date") else ""
        intro.append(f"{day.get('label')}{date_text}：{day.get('title')}。{slot}")

    experience_details: list[dict[str, Any]] = []
    knowledge = KnowledgeService(db)
    for item in experiences:
        start = str(item.get("start_time") or "")[:5]
        end = str(item.get("end_time") or "")[:5]
        duration_text = "按当天行程安排"
        if start and end:
            try:
                start_minutes = int(start[:2]) * 60 + int(start[3:5])
                end_minutes = int(end[:2]) * 60 + int(end[3:5])
                span = end_minutes - start_minutes
                if span <= 0:
                    span += 24 * 60
                hours, minutes = divmod(span, 60)
                duration_text = f"约 {hours} 小时" + (f" {minutes} 分钟" if minutes else "")
            except ValueError:
                duration_text = "按当天行程安排"
        address = str(item.get("address") or stay.get("hotel_address") or "")
        extra = "已包含在套餐价格内，无需为该体验另付费用。"
        source_note = ""
        match = knowledge.search(str(item.get("resource_name") or ""), limit=1)
        if match:
            source_note = f"{match[0]['description']}（来源：{match[0]['source_name']}）"
        experience_details.append(
            {
                "name": str(item.get("resource_name") or ""),
                "time": f"{start}–{end}" if start and end else "按当天行程安排",
                "duration": duration_text,
                "address": address,
                "included": "已含在套餐价格内",
                "extra_cost": extra,
                "feature": str(item.get("description") or ""),
                "tips": str(item.get("booking_notice") or "建议提前 10 分钟到场，按现场工作人员引导体验。"),
                "source_note": source_note,
            }
        )

    spend_notes = [
        f"套餐价 ¥{data.get('suggested_price')} 起，含 {nights} 晚{room_name}住宿、上述 {len(experiences)} 项体验、酒店服务与现场引导。",
        "不含往返大交通、套餐外餐饮与个人消费；酒店内早餐以外的加餐、洗衣、迷你吧等按酒店标准另计。",
        "体验点周边餐饮、纪念品与个人消费不包含在套餐价内。",
    ]

    areas = {word for word in ("西湖", "湖滨", "运河", "拱宸桥", "南山", "良渚", "西溪", "湘湖", "龙井", "钱江", "河坊街") if word in " ".join(item["address"] + item["feature"] for item in experience_details)}
    route_segments: list[str] = []
    for day_route in data.get("route_plan") or []:
        stops = day_route.get("stops") or []
        for index, leg in enumerate(day_route.get("legs") or []):
            if index + 1 >= len(stops):
                continue
            source, target = stops[index], stops[index + 1]
            minutes = int(leg.get("minutes") or 0)
            if minutes:
                route_segments.append(
                    f"{source.get('title')}（{source.get('address')}）→{target.get('title')}（{target.get('address')}），预留约 {minutes} 分钟"
                )
    cancellation_rules = list(dict.fromkeys(
        str(item.get("cancellation_rule") or "").strip()
        for item in resources
        if str(item.get("cancellation_rule") or "").strip()
    ))
    tips = [
        ("路线衔接：" + "；".join(route_segments)) if route_segments else f"路线安排：住宿与体验点位于{'、'.join(sorted(areas)) + '一带' if areas else '杭州'}，按行程顺序衔接。",
        "场次安排：按页面列出的时段出发，提前 10 分钟到达集合点。",
        ("退改说明：" + "；".join(cancellation_rules)) if cancellation_rules else "退改说明：下单时会展示本产品的退改规则。",
        f"随身建议：{ '户外项目请穿方便行走的鞋，夏天带防晒与驱蚊；' if any(word in ' '.join(item['feature'] for item in experience_details) for word in ('户外', '散步', '骑行', '湿地')) else '室内项目为主，带一件薄外套应对空调温差；' }儿童同行请携带常用药品与饮用水。",
    ]
    result = {"intro": intro, "experience_details": experience_details, "spend_notes": spend_notes, "tips": tips}
    copy_overrides = (data.get("visitor_copy") or {}).get("detail_sections") or {}
    for key in ("intro", "spend_notes", "tips"):
        values = copy_overrides.get(key)
        if isinstance(values, list):
            result[key] = [public_travel_copy(value, "") for value in values if isinstance(value, str) and value.strip()]
    experience_overrides = copy_overrides.get("experience_details") or []
    if isinstance(experience_overrides, list):
        for index, override in enumerate(experience_overrides):
            if index >= len(experience_details) or not isinstance(override, dict):
                continue
            for field in ("feature", "tips"):
                value = override.get(field)
                if isinstance(value, str) and value.strip():
                    experience_details[index][field] = public_travel_copy(value, str(experience_details[index].get(field) or ""))
    return result


def safe_product_context(db: Session, product: TravelProduct) -> dict[str, Any]:
    """Return only visitor-safe facts for Visitor Skill explanations."""
    room = db.get(RoomInventory, product.room_inventory_id)
    resources: list[dict[str, Any]] = []
    for row in product.resources:
        item: dict[str, Any] = {
            "name": row.resource_name,
            "type": "住宿" if row.resource_type == "ROOM" else "酒店内服务" if row.resource_type == "HOTEL_SERVICE" else "杭州体验",
            "quantity_per_package": row.quantity_per_package,
        }
        source = room if row.resource_type == "ROOM" else db.get(HotelService if row.resource_type == "HOTEL_SERVICE" else PartnerResource, row.resource_id)
        if source is not None:
            item.update({
                "category": getattr(source, "service_type", None) or getattr(source, "category", None),
                "start_time": source.start_time.strftime("%H:%M") if getattr(source, "start_time", None) else None,
                "end_time": source.end_time.strftime("%H:%M") if getattr(source, "end_time", None) else None,
                "address": getattr(source, "address", None),
                "indoor": getattr(source, "indoor", None),
                "weather_tags": getattr(source, "weather_tags", None),
                "minimum_age": getattr(source, "minimum_age", None),
                "maximum_age": getattr(source, "maximum_age", None),
            })
        resources.append(item)
    return {
        "id": product.id,
        "product_name": product.product_name,
        "theme": product.theme,
        "target_crowd": product.target_crowd,
        "weather": product.weather,
        "target_date": product.target_date.isoformat(),
        "price": str(product.suggested_price),
        "sale_quantity": product.sale_quantity,
        "room_max_guests": room.max_guests if room else None,
        "resources": resources,
        "recommendation_reason": product.recommendation_reason,
    }


def alternative_products(db: Session, current: TravelProduct | None, request: VisitorRecommendRequest) -> list[TravelProduct]:
    """Rank visible alternatives without requiring an exact duplicate date.

    A traveller asking "还有什么" should get useful cards even when the same
    theme is not stocked on the exact date.  We prefer exact date/crowd/budget
    matches, then relax only the date while retaining the remaining signals.
    """

    scored: list[tuple[int, TravelProduct]] = []
    for item in list_products(db, public_only=True):
        if current and item.id == current.id:
            continue
        score = 0
        if request.target_date:
            score += 7 if item.target_date == request.target_date else 0
        if item.target_crowd == request.target_crowd:
            score += 5
        elif item.target_crowd == "ALL":
            score += 2
        if item.suggested_price <= request.budget:
            score += 4
        else:
            score -= min(4, int((item.suggested_price - request.budget) / Decimal("200")) + 1)
        child_ok, weather_ok, interest_ok, _, negative_hit = matches_conditions(db, item, request)
        if negative_hit:
            continue
        score += 3 if child_ok else -3
        score += 3 if weather_ok else -2
        score += 3 if interest_ok else 0
        if current and item.theme != current.theme:
            score += 1
        if item.sale_quantity > 3:
            score += 1
        scored.append((score, item))
    scored.sort(key=lambda pair: (pair[0], pair[1].sale_quantity, -float(pair[1].suggested_price)), reverse=True)
    return [item for _, item in scored[:3]]


def matches_conditions(db: Session, product: TravelProduct, request: VisitorRecommendRequest) -> tuple[bool, bool, bool, int, bool]:
    children_match = True
    weather_match = True
    room = db.get(RoomInventory, product.room_inventory_id)
    if not room or request.adult_count + request.child_count > room.max_guests:
        children_match = False
    for row, resource in product_partner_rows(db, product):
        if not is_weather_supported(resource.weather_tags, request.weather):
            weather_match = False
        if request.arrival_time and resource.start_time and resource.start_time < request.arrival_time:
            children_match = False
        if not crowd_supported(resource.suitable_crowds, product.target_crowd, request.child_ages, resource.minimum_age, resource.maximum_age):
            children_match = False
    if request.child_count and len(request.child_ages) != request.child_count:
        children_match = False
    searchable = f"{product.product_name} {product.theme} {product.marketing_content}"
    resource_categories: set[str] = set()
    for row, resource in product_partner_rows(db, product):
        searchable += f" {resource.resource_name} {resource.address} {resource.description}"
        resource_categories.add(str(resource.category).upper())
    interest_terms = [*request.interests, *request.requested_places]
    semantic_categories = preference_categories(searchable)
    requested_categories = {item.upper() for item in request.interests if str(item).upper() in PREFERENCE_ALIASES}
    requested_categories.update(preference_categories(" ".join(str(item) for item in request.interests)))
    negative_categories = {item.upper() for item in request.negative_interests}
    negative_categories.update(preference_categories(request.natural_language) & negative_preference_categories(request.natural_language))
    negative_hit = bool(negative_categories & semantic_categories) or bool(negative_categories & resource_categories)
    persona_match = product.target_crowd in {request.target_crowd, "ALL"} if request.target_crowd else True
    activity_match = True
    if request.activity_level == "LOW" and any(category in resource_categories for category in {"SPORT", "NATURE", "CITY_WALK"}):
        activity_match = False
    if request.activity_level == "HIGH" and not any(category in resource_categories for category in {"SPORT", "THEME_PARK", "ENTERTAINMENT", "NIGHTLIFE"}):
        activity_match = False
    positive_match = not interest_terms or any(item.lower() in searchable.lower() for item in interest_terms) or bool(requested_categories & semantic_categories)
    # A negative preference only excludes a product that actually contains the
    # unwanted category. It must never make every alternative disappear.
    interest_match = persona_match and activity_match and not negative_hit and positive_match
    budget_match = product.suggested_price <= request.budget
    score = (35 if budget_match else 0) + (25 if children_match else 0) + (20 if weather_match else 0) + (20 if interest_match else 0)
    # `negative_hit` is returned separately so callers can hard-exclude a
    # product the traveller explicitly ruled out instead of merely ranking it
    # lower.
    return children_match, weather_match, interest_match, score, negative_hit


def build_schedule(db: Session, product: TravelProduct, arrival: time | None = None, preferred: time | None = None) -> list[dict[str, str]]:
    check_in = max(time(15, 0), arrival or time(15, 0))
    schedule = [{"time": check_in.strftime("%H:%M"), "title": "办理入住", "description": "到店后办理入住，稍作休息再出发"}]
    for row in product.resources:
        if row.resource_type == "HOTEL_SERVICE":
            service = db.get(HotelService, row.resource_id)
            if service and service.start_time and (not arrival or service.start_time >= arrival):
                schedule.append({"time": service.start_time.strftime("%H:%M"), "title": service.service_name, "description": "可以慢慢享用"})
        elif row.resource_type == "PARTNER_RESOURCE":
            resource = db.get(PartnerResource, row.resource_id)
            if resource and resource.start_time and (not arrival or resource.start_time >= arrival):
                schedule.append({"time": resource.start_time.strftime("%H:%M"), "title": resource.resource_name, "description": f"地址：{resource.address}"})
    schedule.sort(key=lambda item: item["time"])
    if preferred:
        schedule.append({"time": preferred.strftime("%H:%M"), "title": "游客偏好时段", "description": "具体时间会在出行前和你确认"})
    return schedule


@router.get("/guides")
def guides(
    query: str = Query(default="杭州旅行", max_length=80),
    near: str = Query(default="", max_length=120, description="当前产品所在的片区，用于过滤距离过远的景点"),
    limit: int = Query(default=4, ge=1, le=8),
    db: Session = Depends(get_db),
):
    """Public guide notes taken from the knowledge base, quoted as stored.

    Experience pages previously rendered one of eight hand-written templates,
    so every product ended up with nearly identical "参考路线".  The visitor
    page now quotes the curated records themselves (description, opening
    hours, reservation notice and source), which keeps the text attached to
    the actual place and varies by query.
    """

    service = KnowledgeService(db)
    matches = service.search(query, limit=limit)
    if not matches:
        fallback = re.sub(r"[·｜|、，,]+", " ", query.strip() or "杭州")[:40].strip() or "杭州"
        matches = service.search(fallback, limit=limit)
    if near and matches:
        # Only keep records in the same part of the city as the product; a
        # museum on the other side of Hangzhou is not a useful reference.
        anchors = area_tokens(near)
        if anchors:
            near_matches = [
                item for item in matches if area_tokens(item.get("address"), item.get("area"), item.get("name")) & anchors
            ]
            if near_matches:
                matches = near_matches
    guides: list[dict[str, Any]] = []
    for item in matches:
        stay_minutes = item.get("suggested_duration_minutes")
        summary_parts = [part for part in (item.get("area"), item.get("indoor_outdoor_label")) if part]
        if stay_minutes:
            summary_parts.append(f"建议停留 {stay_minutes} 分钟")
        # Keep the stored wording; only collapse whitespace for display.
        description = re.sub(r"\s+", " ", str(item.get("description") or "")).strip()
        opening = re.sub(r"\s+", " ", str(item.get("opening_hours") or "")).strip()
        reservation = re.sub(r"\s+", " ", str(item.get("reservation_notice") or "")).strip()
        content_parts = [
            description,
            f"开放时间：{opening}" if opening else "",
            f"预约提示：{reservation}" if reservation else "",
        ]
        guides.append(
            {
                "source": item.get("source_name") or "公开来源",
                "title": f"{item.get('name')}｜{item.get('category_label') or item.get('category')}",
                "summary": " · ".join(str(part) for part in summary_parts) or "公开资料",
                "content": " ".join(part for part in content_parts if part),
                "url": item.get("source_url") or "",
                "verified_at": item.get("verified_at"),
                "verification_status": item.get("verification_status"),
                # Practical detail so the section reads like a plan, not a link list.
                "address": item.get("address") or "",
                "area": item.get("area") or "",
                "category_label": item.get("category_label") or item.get("category") or "",
                "crowds_label": item.get("suitable_crowds_label") or "",
                "weather_label": item.get("weather_adaptations_label") or "",
                "duration_minutes": stay_minutes,
                "opening_hours": opening,
                "reservation_notice": reservation,
                "best_time": (
                    "上午人少、光线好，适合看展与步行"
                    if (stay_minutes or 0) >= 120
                    else "傍晚或日落前后最舒服，之后可顺路用餐"
                ),
                "transport": (
                    f"位于{item.get('area') or '杭州'}，从酒店出发按当天交通约 20–40 分钟；"
                    f"{'地铁 + 步行' if (item.get('indoor_outdoor') or '') != 'OUTDOOR' else '打车或地铁 + 步行'}都方便。"
                ),
            }
        )
    if guides:
        return guides
    # Last resort only: the knowledge base is empty or unreachable.
    from urllib.parse import quote

    clean = re.sub(r"[·｜|、，,]+", " ", query.strip() or "杭州旅行")
    clean = re.sub(r"杭州一晚|杭州周末|体验|住宿", "", clean).strip() or "杭州旅行"
    encoded = quote(clean)
    return [
        {
            "source": "公开检索",
            "title": f"{clean}相关公开资料",
            "summary": "知识库暂未收录该地点",
            "content": f"知识库暂未收录“{clean}”的公开资料，可在管理端补充来源后再引用；当前建议以购买确认中的集合时间与地址为准。",
            "url": f"https://www.xiaohongshu.com/search_result?keyword={encoded}",
        }
    ]

def compact_product_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Strip detail-only fields from product cards while preserving ProductRead compatibility."""
    compact = dict(data)
    compact["marketing_content"] = ""
    compact["marketing_assets"] = []
    compact["resources"] = []
    compact["day_plan"] = []
    compact["route_plan"] = []
    compact["detail_sections"] = None
    compact["reviews"] = []
    compact["rating_average"] = None
    compact["rating_count"] = 0
    return compact


@router.get("/products", response_model=list[ProductRead])
def products(
    query: VisitorProductQuery = Depends(),
    nights: int = Query(default=1, ge=1, le=3, description="入住晚数；产品以酒店房态为锚点，最少 1 晚"),
    compact: bool = Query(default=False, description="仅返回商品卡片字段"),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    if sweep_expired_intents(db):
        db.commit()
    cache: dict = {}
    all_items = public_items(db, query, limit=limit, offset=offset)
    items = [visitor_payload(db, item, nights=nights, cache=cache) for item in all_items]
    return [compact_product_payload(item) for item in items] if compact else items


def _room_pool_remaining(db: Session, hotel_id: int, room_type: str, target_date: date) -> int:
    """Sellable rooms for one room type on one night (shared by all packages)."""

    pool = db.scalar(
        select(func.max(RoomInventory.available_count)).where(
            RoomInventory.hotel_id == hotel_id,
            RoomInventory.room_type == room_type,
            RoomInventory.available_date == target_date,
        )
    )
    committed = db.scalar(
        select(func.count())
        .select_from(VisitorIntent)
        .join(TravelProduct, VisitorIntent.product_id == TravelProduct.id)
        .join(RoomInventory, RoomInventory.id == TravelProduct.room_inventory_id)
        .where(
            RoomInventory.hotel_id == hotel_id,
            RoomInventory.room_type == room_type,
            TravelProduct.target_date == target_date,
            VisitorIntent.reservation_status.in_(("CONFIRMED", "HELD")),
        )
    )
    return max(0, int(pool or 0) - int(committed or 0))


@router.get("/products/{product_id}/dates")
def product_dates(product_id: int, db: Session = Depends(get_db)):
    """Other departure dates for the same package, so a traveller can switch."""

    product = get_product(db, product_id)
    if not product or not is_publicly_sellable(product):
        raise AppError("NOT_FOUND", "当前套餐不存在或已下架", status_code=404)
    cache: dict = {}
    # Collect every departure date this hotel actually sells.  A package whose
    # own theme appears on a single date would otherwise offer a one-item date
    # picker, so we look at the whole hotel calendar and keep the best product
    # per date (preferring the same theme, then the one with the most rooms).
    best: dict[date, dict[str, Any]] = {}
    for item in list_products(db, public_only=True):
        # 同一套餐的其他出行日期：只换日期，不换产品内容。
        if item.hotel_id != product.hotel_id or item.theme != product.theme:
            continue
        room = db.get(RoomInventory, item.room_inventory_id)
        payload = visitor_payload(db, item, cache=cache)
        remaining = int(payload.get("sale_quantity") or 0)
        same_theme = item.theme == product.theme
        candidate = {
            "id": item.id,
            "target_date": item.target_date.isoformat(),
            "weekday": "周" + "一二三四五六日"[item.target_date.weekday()],
            "sale_quantity": remaining,
            "status": payload.get("status"),
            "price": str(item.suggested_price),
            "room_type": str(getattr(room, "room_type", "") or ""),
            "theme": item.theme,
            "same_theme": same_theme,
        }
        current = best.get(item.target_date)
        if current is None:
            best[item.target_date] = candidate
        elif same_theme and not current["same_theme"]:
            best[item.target_date] = candidate
        elif same_theme == current["same_theme"] and remaining > int(current["sale_quantity"]):
            best[item.target_date] = candidate
    dates = sorted(best.values(), key=lambda row: row["target_date"])
    return {"theme": product.theme, "dates": dates[:20]}


@router.get("/products/{product_id}/rooms")
def product_rooms(product_id: int, db: Session = Depends(get_db)):
    """Every room type this package can be booked with on its departure date."""

    product = get_product(db, product_id)
    if not product or not is_publicly_sellable(product):
        raise AppError("NOT_FOUND", "当前套餐不存在或已下架", status_code=404)
    base_room = db.get(RoomInventory, product.room_inventory_id)
    base_price = Decimal(str(product.suggested_price or 0))
    base_normal = Decimal(str(getattr(base_room, "normal_price", 0) or 0))
    rooms = list(
        db.scalars(
            select(RoomInventory).where(
                RoomInventory.hotel_id == product.hotel_id,
                RoomInventory.available_date == product.target_date,
                RoomInventory.status == "AVAILABLE",
            )
        ).all()
    )
    by_type: dict[str, RoomInventory] = {}
    for room in rooms:
        current = by_type.get(str(room.room_type))
        if current is None or int(room.available_count or 0) > int(current.available_count or 0):
            by_type[str(room.room_type)] = room
    options: list[dict[str, Any]] = []
    for room_type, room in by_type.items():
        delta = Decimal(str(room.normal_price or 0)) - base_normal
        remaining = _room_pool_remaining(db, product.hotel_id, room_type, product.target_date)
        options.append(
            {
                "room_inventory_id": room.id,
                "room_type": room_type,
                "max_guests": int(room.max_guests or 0),
                "features": str(room.features or ""),
                "price": str((base_price + delta).quantize(Decimal("0.01"))),
                "price_delta": str(delta.quantize(Decimal("0.01"))),
                "sale_quantity": remaining,
                "available": remaining > 0,
                "is_current": room.id == product.room_inventory_id,
            }
        )
    options.sort(key=lambda row: (not row["is_current"], not row["available"], Decimal(row["price"])))
    return {"product_id": product.id, "date": product.target_date.isoformat(), "rooms": options}


@router.get("/products/{product_id}", response_model=ProductRead)
def product_detail(
    product_id: int,
    nights: int = Query(default=1, ge=1, le=3, description="入住晚数；不足时自动降级为可售晚数"),
    room_inventory_id: int | None = Query(default=None, ge=1, description="按其他房型查看同一套餐"),
    db: Session = Depends(get_db),
):
    if sweep_expired_intents(db):
        db.commit()
    product = get_product(db, product_id)
    # A sold-out room type still opens: the page shows the sold-out state and
    # the alternatives for the same date instead of a dead end.
    if not product or not is_publicly_sellable(product):
        raise AppError("NOT_FOUND", "当前套餐不存在或已下架", status_code=404)
    data = visitor_payload(db, product, nights=nights)
    if room_inventory_id and room_inventory_id != product.room_inventory_id:
        # One package, several room types: swap the room and re-price it.
        room = db.get(RoomInventory, room_inventory_id)
        base_room = db.get(RoomInventory, product.room_inventory_id)
        old_room_name = str(data.get("stay", {}).get("room_name") or "")
        if room and room.available_date == product.target_date:
            delta = Decimal(str(room.normal_price or 0)) - Decimal(str(getattr(base_room, "normal_price", 0) or 0))
            data["suggested_price"] = str((Decimal(str(product.suggested_price)) + delta).quantize(Decimal("0.01")))
            for resource in data.get("resources", []):
                if resource.get("resource_type") == "ROOM":
                    resource["resource_name"] = str(room.room_type)
                    resource["description"] = str(room.features or room.room_type)
                    resource["image_url"] = str(getattr(room, "image_url", "") or "")
                    resource["image_source"] = str(getattr(room, "image_source", "") or "")
                    resource["image_attribution"] = str(getattr(room, "image_attribution", "") or "")
            stay = data.get("stay") or {}
            stay["room_name"] = str(room.room_type)
            stay["room_type"] = str(room.room_type)
            stay["price"] = data["suggested_price"]
            # 多晚价格选项也要跟着新房型重算。
            for option in stay.get("options") or []:
                try:
                    option["price"] = str((Decimal(str(option.get("price") or 0)) + delta).quantize(Decimal("0.01")))
                except (TypeError, ValueError):
                    continue
            data["stay"] = stay
            remaining = _room_pool_remaining(db, product.hotel_id, str(room.room_type), product.target_date)
            data["sale_quantity"] = remaining
            data["listed_quantity"] = remaining
            data["sold_quantity"] = max(0, int(product.listed_quantity or 0) - remaining)
            data["room_inventory_id"] = room.id
            if remaining <= 0:
                data["status"] = "SOLD_OUT"
            elif remaining <= 2 and str(data.get("status")) == "ON_SALE":
                data["status"] = "LOW_STOCK"
            # 行程 / 路线里也会出现房型名（例如「今晚继续入住庭院主题房」），
            # 一并替换，保证切换房型后整页文字都跟着变。
            if old_room_name and str(room.room_type) != old_room_name:
                blob = json.dumps(
                    {"day_plan": data.get("day_plan"), "route_plan": data.get("route_plan")},
                    ensure_ascii=False,
                ).replace(old_room_name, str(room.room_type))
                swapped = json.loads(blob)
                data["day_plan"] = swapped["day_plan"]
                data["route_plan"] = swapped["route_plan"]
    # Build the detail copy AFTER the room swap so 「费用 / 亮点 / 出行建议」里的
    # 房型、价格和场次都跟着当前选中的房型一起刷新，而不是停留在初始房型。
    data["detail_sections"] = build_detail_sections(db, product, data)
    return data


@router.get("/products/{product_id}/alternatives")
def product_alternatives(product_id: int, db: Session = Depends(get_db)):
    """Other room types and other packages for the same departure date.

    The detail page uses this both for the room-type selector and for switching
    a traveller to a comparable package when a room type is sold out.
    """

    product = get_product(db, product_id)
    if not product:
        raise AppError("NOT_FOUND", "当前套餐不存在或已下架", status_code=404)
    current_room = db.get(RoomInventory, product.room_inventory_id)
    current_type = str(getattr(current_room, "room_type", "") or "")
    cache: dict = {}
    room_types: list[dict[str, Any]] = []
    same_room: list[dict[str, Any]] = []
    seen_types: set[str] = set()
    for item in list_products(db, hotel_id=product.hotel_id):
        # Show every package the hotel has published for this date, including
        # the ones whose shared room pool is already gone: the selector marks
        # them 已售完 instead of silently hiding a like-for-like alternative.
        if item.id == product.id or item.target_date != product.target_date:
            continue
        if str(item.status) not in {"ON_SALE", "LOW_STOCK", "SOLD_OUT"}:
            continue
        room = db.get(RoomInventory, item.room_inventory_id)
        if room is None:
            continue
        payload = visitor_payload(db, item, cache=cache)
        entry = {
            "id": item.id,
            "product_name": item.product_name,
            "theme": item.theme,
            "room_type": str(room.room_type),
            "max_guests": int(room.max_guests or 0),
            "price": str(item.suggested_price),
            "stay_label": (payload.get("stay") or {}).get("label") or "2天1晚",
            "sale_quantity": int(payload.get("sale_quantity") or 0),
            "status": payload.get("status"),
            "experiences": [row.resource_name for row in item.resources if row.resource_type != "ROOM"][:3],
        }
        if str(room.room_type) == current_type:
            same_room.append(entry)
        elif str(room.room_type) not in seen_types:
            seen_types.add(str(room.room_type))
            room_types.append(entry)
    room_types.sort(key=lambda row: (row["sale_quantity"] <= 0, Decimal(row["price"])))
    same_room.sort(key=lambda row: (row["sale_quantity"] <= 0, Decimal(row["price"])))
    return {
        "date": product.target_date.isoformat(),
        "current_room_type": current_type,
        "room_types": room_types[:8],
        "same_room_packages": same_room[:12],
    }



def product_area_tokens(db: Session, product: TravelProduct) -> set[str]:
    """Area tokens for one product, read from the linked resource rows.

    ``ProductResource`` only stores a type + id, so the concrete address has to
    come from the partner or hotel-service record it points at.  Reading a
    non-existent ``ProductResource.address`` used to raise and break the whole
    visitor consult/recommend flow.
    """

    addresses: list[str] = []
    for row in product.resources:
        if row.resource_type == "PARTNER_RESOURCE":
            partner = db.get(PartnerResource, row.resource_id)
            if partner and getattr(partner, "address", ""):
                addresses.append(str(partner.address))
        elif row.resource_type == "HOTEL_SERVICE":
            service = db.get(HotelService, row.resource_id)
            if service and getattr(service, "address", ""):
                addresses.append(str(service.address))
        if row.resource_name:
            addresses.append(str(row.resource_name))
    if product.theme:
        addresses.append(str(product.theme))
    return area_tokens(*addresses)


def recommendation_searchable_text(db: Session, product: TravelProduct) -> str:
    """Build the visitor-safe text index used by assistant recommendations.

    Include every sellable resource, not only the partner rows.  This makes a
    request such as “想住带投影的房间、顺便看展” match the actual package
    contents instead of relying on a repeated generated title.
    """
    parts = [product.product_name, product.theme, product.marketing_title, product.marketing_content]
    for row in product.resources:
        parts.extend([
            row.resource_name,
            getattr(row, "address", "") or "",
            getattr(row, "description", "") or "",
            row.resource_type,
        ])
        if row.resource_type == "PARTNER_RESOURCE":
            partner = db.get(PartnerResource, row.resource_id)
            if partner:
                parts.extend([
                    partner.resource_name,
                    partner.category or "",
                    partner.address or "",
                    partner.description or "",
                ])
        elif row.resource_type == "HOTEL_SERVICE":
            service = db.get(HotelService, row.resource_id)
            if service:
                parts.extend([
                    service.service_name,
                    service.service_type or "",
                    getattr(service, "features", "") or "",
                ])
        elif row.resource_type == "ROOM":
            room = db.get(RoomInventory, row.resource_id) or db.get(RoomInventory, product.room_inventory_id)
            if room:
                parts.extend([
                    room.room_type or "",
                    getattr(room, "features", "") or "",
                    getattr(room, "tags", "") or "",
                ])
    return " ".join(str(part or "") for part in parts).lower()


def recommendation_group_key(product: TravelProduct) -> str:
    """Collapse duplicate date variants so cards show distinct experiences."""
    core = [product.theme or product.product_name]
    core.extend(
        row.resource_name
        for row in product.resources
        if row.resource_type == "PARTNER_RESOURCE"
    )
    value = " ".join(core).lower()
    value = re.sub(r"[0-9０-９]+|[年月日/_.·•｜|：:、，,\s]+", "", value)
    return value or str(product.id)


def choose_assistant_products(
    scored: list[tuple[int, bool, TravelProduct]],
    *,
    current_id: int | None,
    seed_text: str,
    limit: int = 4,
) -> tuple[list[TravelProduct], int]:
    """Pick varied cards while retaining the strongest direct matches first.

    The stable seed keeps one conversation deterministic, while different
    questions/conversations rotate tied date variants.  Group de-duplication
    prevents the assistant from showing the same package three times merely
    because it has different dates or inventory rows.
    """
    seed = sum((index + 1) * ord(char) for index, char in enumerate(seed_text))
    def ranked(values: list[tuple[int, bool, TravelProduct]]) -> list[tuple[int, bool, TravelProduct]]:
        result = sorted(
            values,
            key=lambda item: (item[0], (item[2].id * 2654435761 + seed) % 1000003),
            reverse=True,
        )
        # Rotate a small high-quality window for each conversation/question.
        # Scores still decide the window, while tied date variants no longer
        # make every visitor see the same first three cards.
        window = min(len(result), max(limit * 2, 6))
        if window > 2:
            # The strongest match always stays first; the rest of the window
            # rotates so a visitor does not see the identical shortlist twice.
            head = result[0]
            tail = result[1:window]
            offset = seed % len(tail)
            result = [head, *tail[offset:], *tail[:offset], *result[window:]]
        return result

    ordered = ranked([item for item in scored if item[1]]) + ranked([item for item in scored if not item[1]])
    selected: list[TravelProduct] = []
    direct_count = 0
    groups: set[str] = set()
    for _, direct, product in ordered:
        if current_id is not None and product.id == current_id:
            continue
        group = recommendation_group_key(product)
        if group in groups:
            continue
        groups.add(group)
        selected.append(product)
        if direct:
            direct_count += 1
        if len(selected) >= limit:
            break
    return selected, direct_count


def tidy_punctuation(text: str) -> str:
    """Collapse the "。、" / "，。" style punctuation runs the model sometimes emits.

    Every visitor-facing sentence (greeting, follow-up chips, concierge answer)
    goes through here so a reader never sees a full stop and a comma glued
    together at the end of a clause.
    """

    if not text:
        return ""
    value = str(text)
    value = re.sub(r"[ \t]+", " ", value)
    # 先处理「。、」「，。」这类相邻标点，保留语气最强的那个。
    value = re.sub(r"。\s*、", "。", value)
    value = re.sub(r"、\s*。", "。", value)
    value = re.sub(r"，\s*。", "。", value)
    value = re.sub(r"。\s*，", "。", value)
    # 再合并连续同类标点。
    value = re.sub(r"、{2,}", "、", value)
    value = re.sub(r"，{2,}", "，", value)
    value = re.sub(r"。{2,}", "。", value)
    return value.strip()


@router.get("/assistant/intro")
def assistant_intro(product_id: int | None = None, db: Session = Depends(get_db)):
    """Opening prompts for the concierge.

    The suggestions come from what the hotel is actually selling well and from
    the product the traveller is currently reading, so the first screen is
    never an empty chat box.
    """

    products = list_products(db, public_only=True)
    products.sort(key=lambda item: int(item.sale_quantity or 0), reverse=True)
    current = get_product(db, product_id) if product_id else None
    suggestions: list[str] = []
    greeting = "你好，我可以按同行人、天气和当前在售的套餐帮你选路线。"
    if current is not None:
        experiences = [row.resource_name for row in current.resources if row.resource_type != "ROOM"][:2]
        label = "、".join(experiences) or current.theme
        greeting = f"关于「{current.product_name}」我都能回答，也可以帮你换房型或换一天。"
        suggestions.extend(
            [
                f"这个套餐里的{label}适合几岁的孩子？",
                "下雨天还适合去吗？",
                "同一天还有哪些房型可选？",
            ]
        )
    for item in products[:3]:
        suggestions.append(f"{item.theme}还有什么可以搭配？")
    weather = WeatherService(db).get_forecast("杭州", date.today())
    if weather.get("advisory"):
        # The advisory already ends with a full stop; keep each suggestion as
        # one clean sentence instead of piling punctuation on top of it.
        advisory = str(weather.get("advisory")).rstrip("。")
        suggestions.append(f"今天{advisory}，行程需要调整吗？")
    suggestions.append("预算 700 左右，一家三口有什么推荐？")
    seen: set[str] = set()
    unique = [item for item in suggestions if item and not (item in seen or seen.add(item))]
    # Normalise trailing punctuation so no suggestion shows a stray "。？" or "，。".
    unique = [
        tidy_punctuation(item.rstrip("。，、").rstrip() + "？")
        if not item.rstrip().endswith(("？", "!", "！", "。"))
        else tidy_punctuation(item)
        for item in unique
    ]
    return {"greeting": tidy_punctuation(greeting), "suggestions": unique[:6]}


@router.post("/consult")
def consult(request: VisitorQuestion, db: Session = Depends(get_db)):
    if sweep_expired_intents(db):
        db.commit()
    product = get_product(db, request.product_id) if request.product_id else None
    if product and (product.status not in {"ON_SALE", "LOW_STOCK"} or product.sale_quantity <= 0):
        product = None
    interpreted_request, _ = enrich_recommend_request(VisitorRecommendRequest(natural_language=request.natural_language or request.question, weather=request.weather, target_crowd=product.target_crowd if product else "FAMILY"))
    asks_for_alternatives = any(word in request.question for word in ("还有", "其他", "推荐", "别的", "换一个", "类似"))
    visible_products = list_products(db, public_only=True)
    payload = {
        "question": request.question,
        "natural_language": request.natural_language or request.question,
        "weather": request.weather,
        "target_crowd": interpreted_request.target_crowd,
        "negative_interests": interpreted_request.negative_interests,
        "activity_level": interpreted_request.activity_level,
        "products": [safe_product_context(db, item) for item in (visible_products if asks_for_alternatives else ([product] if product else visible_products))],
        "allergy_information": "",
    }
    # 让回答能结合「要什么/不要什么」和知识库里的地点资料，而不是只做关键词匹配。
    try:
        payload["knowledge"] = KnowledgeService(db).search(request.question, limit=4)
    except Exception:  # knowledge is optional context, never block the answer
        payload["knowledge"] = []
    payload["wants"] = display_preference_terms(
        [*interpreted_request.interests, *interpreted_request.requested_places]
    )
    payload["avoids"] = display_preference_terms(list(interpreted_request.negative_interests))
    payload["budget"] = str(interpreted_request.budget) if interpreted_request.budget else ""
    # 让助手知道这个套餐当天到底能换哪些房型，而不是只看当前这一间。
    if product is not None:
        base_room = db.get(RoomInventory, product.room_inventory_id)
        base_normal = Decimal(str(getattr(base_room, "normal_price", 0) or 0))
        seen_room_types: set[str] = set()
        room_options: list[dict[str, Any]] = []
        for room in db.scalars(
            select(RoomInventory)
            .where(
                RoomInventory.hotel_id == product.hotel_id,
                RoomInventory.available_date == product.target_date,
                RoomInventory.status == "AVAILABLE",
            )
            .order_by(RoomInventory.normal_price)
        ).all():
            room_type = str(room.room_type)
            if room_type in seen_room_types:
                continue
            seen_room_types.add(room_type)
            remaining = _room_pool_remaining(db, product.hotel_id, room_type, product.target_date)
            delta = Decimal(str(room.normal_price or 0)) - base_normal
            room_options.append(
                {
                    "room_inventory_id": room.id,
                    "room_type": room_type,
                    "max_guests": int(room.max_guests or 0),
                    "features": str(room.features or ""),
                    "price": str((Decimal(str(product.suggested_price)) + delta).quantize(Decimal("0.01"))),
                    "remaining": remaining,
                    "is_current": room.id == product.room_inventory_id,
                }
            )
        payload["room_options"] = room_options
    result = AgentOrchestrator(db, hotel_id=product.hotel_id if product else None, source_channel="WEB_VISITOR", actor_role="VISITOR", conversation_id=request.conversation_id).match_visitor(payload)
    raw_answer = public_travel_copy(
        getattr(result.value, "answer", ""),
        "告诉我同行人数、预算和想去的地方，我会为你挑选合适的杭州玩法。",
    )
    # 模型偶尔会把内部的「产品 60」这种编号念出来；访客只该看到产品名。
    raw_answer = re.sub(r"产品\s*[#＃]?\s*\d+\s*[「『]?", "「", raw_answer)
    raw_answer = raw_answer.replace("「「", "「")
    answer = tidy_punctuation(raw_answer)
    # Recommendations are always computed from the visitor's question.  The model may phrase the answer, but it must never invent a museum/food/etc. product or return stale fixed cards.
    # A question without an explicit budget should not inherit the current
    # package's internal price ceiling.  Otherwise a visitor asking for a
    # museum or photo product would see an empty result just because the
    # opened product happens to cost less.  A free-text budget is still parsed
    # by enrich_recommend_request below.
    effective = VisitorRecommendRequest(
        natural_language=request.question,
        weather=request.weather,
        budget=Decimal("2000"),
        target_date=product.target_date if product else None,
        # The current package is context, not a hard audience filter.  A
        # visitor can ask for a couple, a family or friends from any detail.
        target_crowd="ALL",
    )
    effective, _ = enrich_recommend_request(effective)
    budget_explicit = bool(re.search(r"(?:预算|花费|控制在|不超过|以内)[^0-9]{0,8}\d{3,5}", request.question))
    requested_terms = [*effective.interests, *effective.requested_places]
    display_terms = display_preference_terms(requested_terms)
    requested_categories = preference_categories(" ".join(str(term) for term in requested_terms))
    # Prefer experiences that sit in the same part of the city as whatever the
    # traveller named (or as the product they are currently reading).
    target_areas: set[str] = set()
    for term in requested_terms:
        target_areas |= area_tokens(term)
    if product is not None:
        target_areas |= product_area_tokens(db, product)
    scored: list[tuple[int, bool, TravelProduct]] = []
    weather_relaxed: list[tuple[int, bool, TravelProduct]] = []
    for item in visible_products:
        searchable = recommendation_searchable_text(db, item)
        # Prefer explicit terms; category aliases are expanded by the parser.
        hits = sum(1 for term in requested_terms if str(term).lower() in searchable)
        # A term in the product title or theme is a much stronger signal than
        # one that appears only in day-by-day copy.
        title_text = f"{item.product_name} {item.theme}".lower()
        title_hits = sum(1 for term in requested_terms if str(term).lower() in title_text)
        semantic_categories = preference_categories(searchable)
        direct = hits > 0
        related = bool(requested_categories & semantic_categories)
        if requested_terms and not direct and not related:
            continue
        child_ok, weather_ok, interest_ok, score, negative_hit = matches_conditions(db, item, effective)
        if negative_hit:
            continue
        if item.sale_quantity <= 0 or not child_ok:
            continue
        if budget_explicit and item.suggested_price > effective.budget:
            continue
        if item.target_crowd == effective.target_crowd:
            score += 8
        if effective.target_date and item.target_date == effective.target_date:
            score += 10
        if item.suggested_price <= effective.budget:
            score += 7
        else:
            score -= min(8, int((item.suggested_price - effective.budget) / Decimal("200")) + 1)
        score += hits * 28
        score += title_hits * 20
        if target_areas:
            candidate_areas = product_area_tokens(db, item)
            shared = target_areas & candidate_areas
            if shared:
                score += min(14, 7 * len(shared))
        if related and not direct:
            score += 8
        candidate = (score, direct, item)
        if weather_ok:
            scored.append(candidate)
        elif direct:
            # Keep an explicit place/theme request visible when rain or heat
            # removes every strict match.  The response calls out that the
            # outdoor schedule may need confirmation.
            weather_relaxed.append((score - 22, direct, item))

    seed_text = f"{request.conversation_id}:{request.question}"
    suggestions_items, direct_count = choose_assistant_products(
        scored,
        current_id=product.id if product else None,
        seed_text=seed_text,
        limit=4,
    )
    weather_notice = False
    if requested_terms and not direct_count and weather_relaxed:
        relaxed_items, relaxed_direct_count = choose_assistant_products(
            weather_relaxed,
            current_id=product.id if product else None,
            seed_text=f"{seed_text}:weather",
            limit=4,
        )
        # Explicit matches affected by weather are more useful than unrelated
        # fallbacks, but retain strict related cards when there is room.
        seen = {item.id for item in relaxed_items}
        suggestions_items = [*relaxed_items, *[item for item in suggestions_items if item.id not in seen]][:4]
        direct_count = relaxed_direct_count
        weather_notice = bool(relaxed_items)
    cache = {}
    suggestions = [visitor_payload(db, item, cache=cache) for item in suggestions_items]
    # 模型已经给出带理由的详细回答时保留它；只有在回答缺失或过短时，
    # 才退回「找到 N 个」这种兜底话术。
    if not answer or len(answer) < 30:
        if requested_terms and direct_count:
            related_count = len(suggestions) - direct_count
            answer = f"找到 {direct_count} 个直接匹配“{'、'.join(display_terms)}”的在售产品。"
            if related_count:
                answer += f"另外补充 {related_count} 个相近体验，方便比较。"
            if weather_notice:
                answer += "其中户外项目可能受当前天气影响，购买前会再次确认。"
            answer += "下面卡片可直接打开商品详情。"
        elif requested_terms and suggestions:
            answer = f"暂时没有完全匹配“{'、'.join(display_terms)}”的产品，下面补充了 {len(suggestions)} 个相近体验，方便比较。"
        elif requested_terms:
            answer = f"当前在售产品里没有匹配“{'、'.join(display_terms)}”的体验。可以换一个主题或放宽日期、预算。"
    # Name the actual options so the assistant answer is useful on its own
    # rather than a count that forces the visitor to open every card.
    if suggestions_items:
        highlights: list[str] = []
        for item in suggestions_items[:3]:
            names = [row.resource_name for row in item.resources if row.resource_type != "ROOM"][:2]
            window = ""
            for row in item.resources:
                if row.resource_type == "ROOM":
                    continue
                source = db.get(PartnerResource, row.resource_id)
                if source and source.start_time and source.end_time:
                    window = f" {source.start_time.strftime('%H:%M')}–{source.end_time.strftime('%H:%M')}"
                    break
            highlights.append(
                f"{item.product_name}（{item.target_date}{window} · {'、'.join(names) or '住宿+体验'} · ¥{item.suggested_price}）"
            )
        if suggestions_items[0].product_name not in answer:
            answer = f"{answer.rstrip('。')}。具体可选：" + "；".join(highlights) + "。"
    # 让卡片和回答里点名的产品保持一致：回答里出现过的产品排到最前，
    # 访客点开卡片看到的就是刚刚读到的那个方案。
    named = [item for item in visible_products if item.product_name and str(item.product_name) in answer]
    if named:
        ordered: list[dict[str, Any]] = []
        seen_ids: set[int] = set()
        seen_names: set[str] = set()
        for item in named:
            name = str(item.product_name)
            if name in seen_names:
                continue
            seen_names.add(name)
            ordered.append(visitor_payload(db, item, cache=cache))
            seen_ids.add(item.id)
            if len(ordered) >= 4:
                break
        for row in suggestions:
            if row.get("id") not in seen_ids:
                ordered.append(row)
        # 同一套餐在不同日期会重名，卡片里只留一个。
        deduped: list[dict[str, Any]] = []
        seen_card_names: set[str] = set()
        for row in ordered:
            card_name = str(row.get("product_name") or "")
            if card_name in seen_card_names:
                continue
            seen_card_names.add(card_name)
            deduped.append(row)
        suggestions = deduped[:4]
    return {
        "trace_id": result.trace_id,
        "answer": answer,
        "safety_notes": public_travel_copy(
            getattr(result.value, "safety_notes", ""),
            "如有饮食、儿童陪同或行动安排方面的需求，提交购买信息时告诉酒店即可。",
        ),
        "product": visitor_payload(db, product) if product else None,
        "suggestions": suggestions,
        # 换房型问题直接给出可点链接所需的数据（当前套餐 + 各房型 id/价格/余量）。
        "product_id": product.id if product else None,
        "room_options": payload.get("room_options") or [],
        "follow_up_questions": ["同行人数和儿童年龄是多少？", "更想去西湖、运河、博物馆还是主题乐园？", "这次大约准备花多少？"],
        "fallback_used": result.fallback_used,
    }


@router.post("/interpret", response_model=VisitorInterpretResponse)
def interpret(request: VisitorInterpretRequest):
    effective, interpreted = enrich_recommend_request(VisitorRecommendRequest(natural_language=request.natural_language))
    return {"interpreted_needs": interpreted, "follow_up_questions": follow_up_questions(effective, interpreted)}


@router.post("/recommend")
def recommend(request: VisitorRecommendRequest, db: Session = Depends(get_db)):
    if sweep_expired_intents(db):
        db.commit()
    if request.structured_confirmed:
        interpreted = interpreted_needs(request)
    else:
        request, interpreted = enrich_recommend_request(request)
    candidates = list_products(db, public_only=True)
    if request.target_date:
        candidates = [item for item in candidates if item.target_date == request.target_date]
    valid_candidates = []
    match_meta: dict[int, tuple[bool, bool, bool, int]] = {}
    target_areas = area_tokens(request.natural_language, *request.requested_places)
    for item in candidates:
        if item.sale_quantity <= 0 or item.suggested_price > request.budget:
            continue
        children_match, weather_match, interest_match, score, negative_hit = matches_conditions(db, item, request)
        if negative_hit:
            continue
        if not children_match or not weather_match:
            continue
        if request.target_crowd and item.target_crowd not in {request.target_crowd, "ALL"}:
            continue
        if (request.negative_interests or request.activity_level != "MEDIUM") and not interest_match:
            continue
        if target_areas:
            candidate_areas = product_area_tokens(db, item)
            shared_areas = target_areas & candidate_areas
            if shared_areas:
                score += min(14, 7 * len(shared_areas))
        valid_candidates.append(item)
        match_meta[item.id] = (children_match, weather_match, interest_match, score)
    payload = {
        "adult_count": request.adult_count,
        "child_count": request.child_count,
        "child_ages": request.child_ages,
        "budget": str(request.budget),
        "weather": request.weather,
        "target_crowd": request.target_crowd,
        "interests": request.interests,
        "negative_interests": request.negative_interests,
        "activity_level": request.activity_level,
        "requested_places": request.requested_places,
        "natural_language": request.natural_language,
        "dietary_restrictions": request.dietary_restrictions,
        "allergy_information": request.allergy_information,
        "products": [safe_product_context(db, item) for item in valid_candidates],
    }
    hotel_ids = {item.hotel_id for item in valid_candidates}
    agent_result = AgentOrchestrator(db, hotel_id=next(iter(hotel_ids)) if len(hotel_ids) == 1 else None, source_channel="WEB_VISITOR", actor_role="VISITOR", conversation_id=request.conversation_id).match_visitor(payload)
    output = agent_result.value
    output_ids = set(output.selected_product_ids)
    results = []
    for item in sorted(valid_candidates, key=lambda product: match_meta[product.id][3], reverse=True):
        children_match, weather_match, interest_match, score = match_meta[item.id]
        reason = public_travel_copy(
            output.reasons.get(str(item.id), item.recommendation_reason),
            f"围绕{item.theme or '杭州周末'}安排住宿与在地玩法，适合轻松度过一段杭州时间。",
        )
        adjustments = [
            public_travel_copy(value, "")
            for value in (output.limited_adjustments.get(str(item.id)) or [])
        ]
        adjustments = [value for value in adjustments if value] or [
            "购买信息中可以备注你更喜欢的玩法。",
            "出行前留意酒店发来的确认消息。",
        ]
        results.append({
            "product": visitor_payload(db, item),
            "score": min(100, score),
            "recommendation_reason": reason,
            "budget_match": item.suggested_price <= request.budget,
            "children_match": children_match,
            "weather_match": weather_match,
            "interest_match": interest_match,
            "schedule": build_schedule(db, item, request.arrival_time, request.preferred_experience_time),
            "limited_adjustments": adjustments,
            "allergy_warning": public_travel_copy(output.allergy_warning, "") or None,
        })
    return {"results": results, "trace_id": agent_result.trace_id, "fallback_used": agent_result.fallback_used, "interpreted_needs": interpreted, "provider": getattr(agent_result, "provider", "MOCK"), "skill_name": "stayscape-visitor-matcher", "skill_version": getattr(agent_result, "skill_version", "")}


@router.post("/intents")
async def create_intent(request: VisitorIntentCreate, db: Session = Depends(get_db)):
    if sweep_expired_intents(db):
        db.commit()
    product = db.scalar(
        select(TravelProduct)
        .options(selectinload(TravelProduct.resources), selectinload(TravelProduct.adjustments))
        .where(TravelProduct.id == request.product_id)
        .with_for_update()
    )
    if not product or product.status not in {"ON_SALE", "LOW_STOCK"} or product.sale_quantity <= 0:
        raise AppError("PRODUCT_UNAVAILABLE", "当前套餐已无法购买", retryable=True)
    selected_room = db.get(RoomInventory, request.room_inventory_id or product.room_inventory_id)
    base_room = db.get(RoomInventory, product.room_inventory_id)
    if (
        not selected_room
        or not base_room
        or selected_room.hotel_id != product.hotel_id
        or selected_room.available_date != product.target_date
        or selected_room.status not in {"AVAILABLE", "LOW_STOCK"}
    ):
        raise AppError("ROOM_UNAVAILABLE", "所选房型当前不可购买", field="room_inventory_id", retryable=True)
    price_delta = Decimal(str(selected_room.normal_price or 0)) - Decimal(str(base_room.normal_price or 0))
    effective_price = (Decimal(str(product.suggested_price)) + price_delta).quantize(Decimal("0.01"))
    if effective_price <= 0:
        raise AppError("ROOM_PRICE_INVALID", "所选房型价格无效", field="room_inventory_id", status_code=422)
    effective = VisitorRecommendRequest(
        natural_language=request.natural_language,
        target_date=product.target_date,
        weather=product.weather,
        target_crowd=product.target_crowd,
        adult_count=request.adult_count,
        child_count=request.child_count,
        child_ages=request.child_ages,
        budget=request.budget,
        interests=request.interests,
        negative_interests=request.negative_interests,
        activity_level=request.activity_level,
        dietary_restrictions=request.dietary_restrictions,
        allergy_information=request.allergy_information,
        arrival_time=request.arrival_time,
        preferred_experience_time=request.preferred_experience_time,
        other_requirements=request.other_requirements,
    )
    if request.natural_language.strip() and not request.structured_confirmed:
        effective, _ = enrich_recommend_request(effective)
    if effective.child_count and len(effective.child_ages) != effective.child_count:
        raise AppError("VALIDATION_ERROR", "儿童人数与儿童年龄数量不一致", field="child_ages")
    if effective.adult_count + effective.child_count > int(selected_room.max_guests or 0):
        raise AppError("VISITOR_CONSTRAINT_NOT_MET", "所选房型无法容纳同行人数", field="room_inventory_id", retryable=True)
    # A stated dislike never blocks a purchase: the traveller is buying this
    # specific package, so only capacity and age limits are enforced here.
    children_match, weather_match, _, _, _ = matches_conditions(db, product, effective)
    if not children_match:
        raise AppError("VISITOR_CONSTRAINT_NOT_MET", "同行人数、儿童年龄或到店时间不符合该套餐约束", field="adult_count", retryable=True)
    if not weather_match:
        raise AppError("WEATHER_NOT_SUPPORTED", "该套餐内体验不支持游客填写的天气场景", field="weather", retryable=True)
    if effective_price > effective.budget:
        raise AppError("BUDGET_EXCEEDED", "套餐价格超过游客预算上限", field="budget", retryable=True)

    previous_quantity = product.sale_quantity
    previous_status = product.status
    allocation_snapshot = reserve_product_inventory(db, product, room_inventory_id=selected_room.id)
    allocation_snapshot.update({"product_quantity_before": previous_quantity, "product_status_before": previous_status})
    product.sale_quantity -= 1
    product.status = "SOLD_OUT" if product.sale_quantity <= 0 else ("LOW_STOCK" if product.sale_quantity <= 2 else product.status)
    result = {
        "product_id": product.id,
        "room_inventory_id": selected_room.id,
        "room_type": selected_room.room_type,
        "product_name": product.product_name,
        "submitted_price": str(effective_price),
        "submitted_quantity": previous_quantity,
        "remaining_quantity": product.sale_quantity,
        "status_after_submission": product.status,
        "allergy_information": effective.allergy_information,
    }
    intent_data = {
        "product_id": request.product_id,
        "natural_language": request.natural_language,
        "adult_count": effective.adult_count,
        "child_count": effective.child_count,
        "child_ages": effective.child_ages,
        "budget": effective.budget,
        "interests": effective.interests,
        "negative_interests": effective.negative_interests,
        "activity_level": effective.activity_level,
        "dietary_restrictions": effective.dietary_restrictions,
        "allergy_information": effective.allergy_information,
        "arrival_time": effective.arrival_time,
        "preferred_experience_time": effective.preferred_experience_time,
        "other_requirements": effective.other_requirements or request.natural_language,
        "contact_name": request.contact_name,
        "contact_phone": request.contact_phone,
    }
    intent = VisitorIntent(
        **intent_data,
        recommendation_result=result,
        intent_status="NEW",
        reservation_status="HELD",
        reserved_until=datetime.now(timezone.utc) + timedelta(minutes=settings.visitor_intent_hold_minutes),
        allocation_snapshot=allocation_snapshot,
    )
    db.add(intent)
    db.flush()
    db.add(
        ProductAdjustmentRecord(
            product_id=product.id,
            old_quantity=previous_quantity,
            new_quantity=product.sale_quantity,
            old_price=product.suggested_price,
            new_price=product.suggested_price,
            action="VISITOR_INTENT_RESERVE",
            reason="游客购买套餐，事务性占用客房、酒店服务和合作体验名额",
        )
    )
    for allocation in allocation_snapshot.get("allocations", []):
        db.add(
            ResourceChangeEvent(
                event_type="VISITOR_INTENT_RESERVED",
                resource_type=allocation["resource_type"],
                resource_id=allocation["resource_id"],
                hotel_id=product.hotel_id,
                old_value={"available": allocation["before"]},
                new_value={"available": allocation["after"], "intent_id": intent.id, "product_id": product.id},
                reason="游客订单暂占用套餐底层库存",
                operator_role="VISITOR",
                processed=True,
                processing_result={"product_id": product.id, "intent_id": intent.id},
            )
        )
    reconcile_published_capacity(db, product.hotel_id, priority_product_id=product.id)
    db.commit()
    db.refresh(intent)
    phone = intent.contact_phone
    masked = phone[:3] + "****" + phone[-4:] if len(phone) >= 7 else "***"
    await manager.broadcast(
        product.hotel_id,
        {
            "type": "VISITOR_INTENT_CREATED",
            "title": "收到新的游客订单",
            "message": f"{product.product_name} 剩余 {product.sale_quantity} 套",
            "affectedProducts": [
                {
                    "product_id": product.id,
                    "product_name": product.product_name,
                    "old_quantity": previous_quantity,
                    "new_quantity": product.sale_quantity,
                    "old_status": previous_status,
                    "status": product.status,
                    "action": "VISITOR_INTENT_RESERVE",
                }
            ],
        },
    )
    return {
        "id": intent.id,
        "product_id": intent.product_id,
        "product_name": product.product_name,
        "intent_status": intent.intent_status,
        "reservation_status": intent.reservation_status,
        "reserved_until": intent.reserved_until,
        "submitted_quantity": previous_quantity,
        "remaining_quantity": product.sale_quantity,
        "product_status": product.status,
        "contact_phone_masked": masked,
        "message": "购买信息已提交，已暂占用房量、酒店服务和合作体验名额；酒店会在保留时间内联系确认。",
    }


@router.post("/intents/{intent_id}/cancel")
def cancel_intent(intent_id: int, request: VisitorIntentCancelRequest, db: Session = Depends(get_db)):
    if sweep_expired_intents(db):
        db.commit()
    intent = db.scalar(select(VisitorIntent).where(VisitorIntent.id == intent_id).with_for_update())
    if not intent or intent.contact_phone != request.contact_phone:
        raise AppError("NOT_FOUND", "购买记录不存在或联系方式不匹配", status_code=404)
    if intent.reservation_status not in {"HELD", "CONFIRMED"}:
        return {"id": intent.id, "reservation_status": intent.reservation_status, "message": "该购买记录已经结束，无需重复释放"}
    result = release_intent_inventory(db, intent)
    reconcile_published_capacity(db, intent.product.hotel_id if intent.product else 0)
    db.commit()
    return {"id": intent.id, "reservation_status": intent.reservation_status, "intent_status": intent.intent_status, "message": "购买已取消，余量已释放", "inventory": result}


@router.get("/public-resources")
def public_resources(db: Session = Depends(get_db), weather: str = "RAIN"):
    items = list(db.scalars(select(PublicResource).where(PublicResource.status == "ACTIVE").order_by(PublicResource.id)).all())
    return [{"id": item.id, "resource_name": item.resource_name, "category": item.category, "description": item.description, "address": item.address, "opening_hours": item.opening_hours, "weather_supported": is_weather_supported(item.weather_tags, weather), "source": item.source} for item in items]
