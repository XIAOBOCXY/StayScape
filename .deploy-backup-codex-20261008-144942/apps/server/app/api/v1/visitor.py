import json
import re
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from ...agent import AgentOrchestrator
from ...config import settings
from ...core.exceptions import AppError
from ...db import get_db
from ...models import HotelService, PartnerResource, ProductAdjustmentRecord, ProductResource, PublicResource, ResourceChangeEvent, RoomInventory, TravelProduct, VisitorIntent
from ...repositories.product_repository import get_product, list_products, list_public_products_for_serialization
from ...schemas.products import ProductRead
from ...schemas.visitor import VisitorIntentCancelRequest, VisitorIntentCreate, VisitorInterpretRequest, VisitorInterpretResponse, VisitorProductQuery, VisitorQuestion, VisitorRecommendRequest
from ...services.inventory_service import reconcile_published_capacity, release_intent_inventory, reserve_product_inventory, sweep_expired_intents
from ...services.media_library_service import MediaLibraryService
from ...services.knowledge_service import KnowledgeService
from ...services.weather_service import WeatherService
from ...services.public_copy import localize_internal_labels, public_travel_copy, route_proximity, visitor_product_to_dict
from ...services.serializers import build_product_resource_cache, populate_product_resource_cache
from ...rules.availability_rule import tokens
from ...rules.crowd_rule import crowd_supported
from ...rules.time_rule import intervals_overlap
from ...rules.weather_rule import is_weather_supported
from ..websocket_manager import manager

router = APIRouter(prefix="/visitor", tags=["visitor"])

_VERIFIED_FACT_FIELDS = {
    "name", "category", "area", "address", "indoor_outdoor", "suitable_crowds",
    "minimum_age", "maximum_age", "suggested_duration_minutes", "opening_hours",
    "weather_adaptations", "reservation_notice", "description",
}


def _verified_public_record(record: Any) -> dict[str, Any] | None:
    if not isinstance(record, dict):
        return None
    fields = set(record.get("verified_fields") or [])
    status = str(record.get("verification_status") or record.get("status") or "")
    if status != "ACTIVE" or not record.get("verified_at") or "name" not in fields:
        return None
    cleaned = dict(record)
    for field in _VERIFIED_FACT_FIELDS:
        if field not in fields:
            cleaned[field] = "" if field in {"name", "category", "area", "address", "indoor_outdoor", "suitable_crowds", "opening_hours", "weather_adaptations", "reservation_notice", "description"} else None
    cleaned["verification_status"] = "ACTIVE"
    return cleaned


def _public_planning_context(planning: dict[str, Any]) -> dict[str, Any]:
    sections: dict[str, Any] = {}
    for section_name, records in (planning.get("sections") or {}).items():
        if not isinstance(records, list):
            continue
        if section_name == "workflow_rules":
            sections[section_name] = records
            continue
        safe_records = []
        for record in records:
            safe = _verified_public_record(record)
            if safe:
                safe_records.append(safe)
        if safe_records:
            sections[section_name] = safe_records
    return {"status": planning.get("status", "AVAILABLE"), "sections": sections}


def explicit_budget_amount(text: str) -> Decimal | None:
    prefix = re.search(r"(?:预算(?:上限|大约|约)?|花费|控制在|不超过|以内)\D{0,10}(\d{2,5})", text)
    suffix = re.search(r"(?<!\d)(\d{2,5})\s*(?:元|块|人民币)?\s*(?:左右|上下|以内|以下|预算|预算上限)", text)
    match = prefix or suffix
    if not match:
        return None
    value = match.group(1)
    if not value and len(match.groups()) > 1:
        value = match.group(2)
    return Decimal(value) if value else None


def hard_budget_limit(text: str) -> bool:
    """Only explicit ceiling language makes an assistant budget a hard filter."""
    amount = explicit_budget_amount(text)
    if amount is None:
        return False
    strict_phrases = (
        "严格控制", "必须不超过", "必须控制在", "绝不能超过", "不能超过",
        "不得超过", "不可超过", "不可高于", "一分不超", "只接受预算内",
        "拒绝超预算", "绝不超预算", "最多只能花",
    )
    return any(marker in text for marker in strict_phrases)


def budget_search_ceiling(text: str, amount: Decimal) -> Decimal:
    """Allow a modest tradeoff for a target budget such as“700 左右”."""
    if hard_budget_limit(text):
        return amount
    approximate = any(marker in text for marker in ("左右", "上下", "大约", "约", "差不多"))
    upper_bound = any(marker in text for marker in ("不超过", "以内", "以下", "最高", "最多", "不高于", "封顶"))
    tolerance = Decimal("0.10") if upper_bound else Decimal("0.20") if approximate else Decimal("0.10")
    return (amount * (Decimal("1") + tolerance)).quantize(Decimal("0.01"))


def budget_label(text: str, amount: Decimal) -> str:
    """Describe the visitor's target without implying a soft target was exact."""
    if hard_budget_limit(text):
        return f"不超过 ¥{amount}"
    if any(marker in text for marker in ("不超过", "以内", "以下", "最高", "最多", "不高于", "封顶")):
        return f"预算 ¥{amount} 以内"
    if any(marker in text for marker in ("左右", "上下", "大约", "约", "差不多")):
        return f"约 ¥{amount}"
    return f"预算 ¥{amount}"


def visitor_answer_copy(text: object) -> str:
    """Remove standalone Markdown/punctuation artifacts while preserving prose."""
    value = public_travel_copy(text, "")
    value = re.sub(r"\[[^\]]{1,160}\]\(https?://[^)]+\)", "", value)
    value = re.sub(r"https?://\S+", "", value)
    value = re.sub(r"(?m)^\s*[^。！？\n]{0,48}(?:已核验|待核验)\s*[。！？]?\s*$", "", value)
    lines: list[str] = []
    for raw in value.splitlines():
        line = re.sub(r"^\s*[-*•·∙⋅]+\s*", "", raw).strip()
        if not line or re.fullmatch(r"[\s•·∙⋅;；:：,，、.!?。…—–-]+", line):
            continue
        line = re.sub(r"^[,，、；;:：]+\s*", "", line)
        line = re.sub(r"\*\*(.*?)\*\*", r"\1", line)
        if not line or "已核验" in line or "待核验" in line:
            continue
        if re.search(r"(?:产品|方案)\s*[#＃]?\s*\d+", line):
            continue
        if "以上价格" in line and ("余量" in line or "当前在售产品信息" in line):
            continue
        if "具体入住和体验" in line and ("酒店最终确认" in line or "预订时酒店" in line):
            continue
        lines.append(line)
    result = "\n".join(lines)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return tidy_punctuation(result)


def strip_reference_metadata(value: Any) -> Any:
    """Keep verified facts in agent context, but remove raw URLs and retrieval labels."""
    hidden = {"source_url", "source_name", "source", "verification_status", "verified_at", "verified_fields", "evidence_sources", "notice", "status"}
    if isinstance(value, dict):
        return {key: strip_reference_metadata(item) for key, item in value.items() if key not in hidden}
    if isinstance(value, list):
        return [strip_reference_metadata(item) for item in value]
    return value


def curated_tourism_context(query: str, db: Session, *, poi_limit: int = 4) -> dict[str, Any]:
    """Load source-labelled strategy references and relevant public POIs."""
    root = Path("/opt/stayscape/skills/yusuchengjing-hotel-ops/data")
    recommendation_patterns: list[dict[str, str]] = []
    try:
        planning = KnowledgeService(db).planning_context()
        poi_data = json.loads((root / "tourism_knowledge.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "UNAVAILABLE", "notice": "文旅策划参考资料暂不可用"}
    planning = _public_planning_context(planning)
    normalized = query.lower()
    tokens_ = [token for token in re.split(r"[\s，。；、,.!?！？]+", normalized) if len(token) > 1]
    # The API runs from /app inside Docker while the host-mounted skills live
    # under /opt/stayscape/skills; deriving parents[5] from the container path
    # is invalid and would abort recommendation requests before the fallback.
    pattern_file = Path("/opt/stayscape/skills/stayscape-visitor-matcher/references/travel-recommendation-patterns.json")
    try:
        pattern_data = json.loads(pattern_file.read_text(encoding="utf-8"))
        for item in pattern_data.get("items", []):
            if not isinstance(item, dict):
                continue
            tags = [str(tag).lower() for tag in item.get("tags", [])]
            score = sum(2 for tag in tags if tag and tag in normalized)
            score += sum(1 for token in tokens_ if any(token in tag or tag in token for tag in tags))
            if score or any(term in normalized for term in ("推荐", "预算", "亲子", "周末", "安排", "杭州")):
                principle = str(item.get("principle") or "").strip()
                if principle:
                    recommendation_patterns.append({
                        "theme": str(item.get("theme") or "杭州文旅策划"),
                        "principle": principle,
                        "fit": str(item.get("fit") or ""),
                    })
        recommendation_patterns = recommendation_patterns[:4]
    except (OSError, json.JSONDecodeError):
        # Strategy references are optional; failure must not block a product match.
        recommendation_patterns = []
    intent_terms = ("西湖", "博物馆", "湿地", "运河", "良渚", "茶", "动漫", "宋城", "演艺", "植物园", "美术馆", "亲子", "户外", "自然", "文化", "非遗", "夜游")
    ranked = []
    for poi in poi_data.get("pois", []):
        text = " ".join(str(poi.get(key, "")) for key in ("name", "category", "description", "district", "address")).lower()
        name = str(poi.get("name", "")).lower()
        score = sum(3 if token in name else 1 for token in tokens_ if token in text)
        score += sum(2 for term in intent_terms if term in normalized and term.lower() in text)
        if name and name in normalized:
            score += 8
        if score:
            ranked.append((score, poi))
    ranked.sort(key=lambda item: item[0], reverse=True)
    places = []
    for _, poi in ranked:
        safe = _verified_public_record(poi)
        if safe:
            places.append(safe)
        if len(places) >= poi_limit:
            break
    source_rows: list[dict[str, str]] = []
    for poi in places:
        source_url = str(poi.get("source_url") or "")
        if source_url.startswith("https://"):
            source_rows.append({
                "title": str(poi.get("name") or "目的地资料"),
                "publisher": str(poi.get("source_name") or ""),
                "url": source_url,
                "verification_status": str(poi.get("verification_status") or "VERIFY_REQUIRED"),
            })
    for section_name, records in planning.get("sections", {}).items():
        if section_name in {"workflow_rules", "project_baseline"} or not isinstance(records, list):
            continue
        for record in records:
            source = record.get("source") if isinstance(record, dict) else None
            if not isinstance(source, dict):
                continue
            relevant = any(term in normalized for term in intent_terms)
            relevant = relevant or any(str(record.get(key) or "").lower() in normalized for key in ("name", "topic") if record.get(key))
            if section_name == "local_context" and any(term in normalized for term in ("杭州", "西湖", "运河", "景区", "行程", "旅游", "文旅")):
                relevant = True
            if relevant and _verified_public_record(record) and str(source.get("url") or "").startswith("https://"):
                source_rows.append({
                    "title": str(source.get("title") or record.get("topic") or record.get("name") or "文旅资料"),
                    "publisher": str(source.get("publisher") or ""),
                    "url": str(source["url"]),
                    "verification_status": str(record.get("status") or "REFERENCE_ONLY"),
                })
    deduped: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for row in source_rows:
        if row["url"] in seen_urls:
            continue
        seen_urls.add(row["url"])
        deduped.append(row)
    return {
        "status": "REFERENCE_ONLY",
        "notice": poi_data.get("notice", "公共目的地资料需按来源与核验状态使用"),
        "planning_context": planning,
        "relevant_public_places": places,
        "recommendation_patterns": recommendation_patterns,
        "evidence_sources": deduped[:5],
    }


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
    if any(word in text for word in ("一家", "亲子", "带娃", "带孩子", "带小朋友", "家庭出行", "一家人")):
        updates["target_crowd"] = "FAMILY"
    elif any(word in text for word in ("情侣", "夫妻", "约会", "两个人", "两人")) and not any(word in text for word in ("孩子", "儿童", "小孩", "小朋友", "岁")):
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
        elif "后天" in text:
            updates["target_date"] = date.today() + timedelta(days=2)
        elif "今天" in text:
            updates["target_date"] = date.today()
        else:
            weekday = parse_weekday(text)
            if weekday:
                updates["target_date"] = weekday
    weather = "RAIN" if any(word in text for word in ("雨", "下雨", "湿冷")) else "SUNNY" if "晴" in text else "CLOUDY" if any(word in text for word in ("多云", "阴天")) else None
    if weather:
        updates["weather"] = weather
    budget_amount = explicit_budget_amount(text)
    if budget_amount is not None:
        updates["budget"] = budget_amount
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


def explicit_calendar_date(text: str, reference_date: date | None = None) -> date | None:
    """Parse the latest explicit date so a follow-up can replace an older date."""
    pattern = re.compile(
        r"(?<!\d)(?P<iso>20\d{2}-\d{1,2}-\d{1,2})(?!\d)"
        r"|(?<!\d)(?:(?P<year>20\d{2})\s*年\s*)?(?P<month>\d{1,2})\s*月\s*(?P<day>\d{1,2})\s*(?:日|号)"
    )
    matches = list(pattern.finditer(text))
    if not matches:
        return None
    match = matches[-1]
    if match.group("iso"):
        year, month, day = (int(value) for value in match.group("iso").split("-"))
    else:
        year = int(match.group("year")) if match.group("year") else (reference_date.year if reference_date else date.today().year)
        month, day = int(match.group("month")), int(match.group("day"))
    try:
        return date(year, month, day)
    except ValueError:
        return None


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
    compact: bool = False,
) -> list[TravelProduct]:
    # The unfiltered landing page is paged in SQL.  Filtered/interest searches
    # still load the bounded public set so ranking is correct, then page the
    # ranked result below instead of applying a limit before matching.
    needs_matching = bool(query and (query.target_date or query.budget_min or query.budget or query.target_crowd or query.interest))
    loader = list_public_products_for_serialization if compact else None
    if loader is not None:
        source = loader(db) if needs_matching else loader(db, limit=limit, offset=offset)
    else:
        source = (
            list_products(db, public_only=True)
            if needs_matching
            else list_products(db, public_only=True, limit=limit, offset=offset)
        )
    products = [item for item in source if is_publicly_sellable(item)]
    if query and query.target_date:
        products = [item for item in products if item.target_date == query.target_date]
    if query and query.budget:
        products = [item for item in products if item.suggested_price <= query.budget]
    if query and query.budget_min:
        products = [item for item in products if item.suggested_price >= query.budget_min]
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


def _room_pool(db: Session, product: TravelProduct) -> tuple[int, str, date] | None:
    room = getattr(product, "room_inventory", None) or db.get(RoomInventory, product.room_inventory_id)
    if room is None or product.target_date is None:
        return None
    return int(product.hotel_id), str(room.room_type), product.target_date


def populate_room_pool_cache(db: Session, cache: dict, products: list[TravelProduct]) -> dict:
    """Cache physical room quantities; reservations already decrement this source."""
    keys = {key for item in products if (key := _room_pool(db, item)) is not None and key not in cache}
    if not keys:
        return cache
    predicates = [and_(RoomInventory.hotel_id == hotel_id, RoomInventory.room_type == room_type,
                       RoomInventory.available_date == target_date)
                  for hotel_id, room_type, target_date in keys]
    pools = {(int(hotel_id), str(room_type), target_date): int(quantity or 0)
             for hotel_id, room_type, target_date, quantity in db.execute(
                 select(RoomInventory.hotel_id, RoomInventory.room_type, RoomInventory.available_date,
                        func.max(RoomInventory.available_count)).where(or_(*predicates)).group_by(
                     RoomInventory.hotel_id, RoomInventory.room_type, RoomInventory.available_date))}
    for key in keys:
        cache[key] = max(0, pools.get(key, 0))
    return cache


def shared_room_remaining(db: Session, product: TravelProduct, cache: dict | None = None) -> int:
    """Physical room availability, capped by this package's remaining quota."""
    pool_key = _room_pool(db, product)
    if pool_key is None:
        return max(0, int(product.sale_quantity or 0))
    if cache is not None and pool_key in cache:
        physical = cache[pool_key]
    else:
        hotel_id, room_type, target_date = pool_key
        physical = db.scalar(select(func.max(RoomInventory.available_count)).where(
            RoomInventory.hotel_id == hotel_id, RoomInventory.room_type == room_type,
            RoomInventory.available_date == target_date)) or 0
        physical = max(0, int(physical))
        if cache is not None:
            cache[pool_key] = physical
    return min(max(0, int(product.sale_quantity or 0)), physical)


def package_room_remaining(db: Session, product: TravelProduct, cache: dict | None = None) -> int:
    """A package is sellable when its base room or any selectable room is available."""
    remaining = shared_room_remaining(db, product, cache)
    if remaining > 0 or not product.target_date:
        return remaining
    alternate_pool = db.scalar(select(func.max(RoomInventory.available_count)).where(
        RoomInventory.hotel_id == product.hotel_id,
        RoomInventory.available_date == product.target_date,
        RoomInventory.status == "AVAILABLE")) or 0
    return min(max(0, int(product.sale_quantity or 0)), max(0, int(alternate_pool)))

def visitor_payload(
    db: Session,
    product: TravelProduct,
    *,
    nights: int = 1,
    cache: dict | None = None,
    include_marketing_assets: bool = True,
    compact: bool = False,
) -> dict[str, Any]:
    """Serialise a product with shared room and source-resource caches."""

    cache = cache if cache is not None else {}
    populate_product_resource_cache(db, cache, [product])
    populate_room_pool_cache(db, cache, [product])
    data = visitor_product_to_dict(
        product,
        nights=nights,
        resource_cache=cache,
        include_marketing_assets=include_marketing_assets,
        compact=compact,
    )
    # Two constraints apply: the product's own listed quota and the room type's
    # shared pool.  The smaller one is what a visitor can actually buy.
    listed = max(0, int(product.listed_quantity or 0))
    remaining = package_room_remaining(db, product, cache)
    data["sale_quantity"] = remaining
    data["listed_quantity"] = remaining
    # 已经卖出的份数 = 发布份数 - 剩余；用于卡片和详情页显示「已售」。
    data["sold_quantity"] = max(0, listed - remaining)
    if remaining <= 0:
        data["status"] = "SOLD_OUT"
    elif remaining <= 2 and str(data.get("status")) == "ON_SALE":
        data["status"] = "LOW_STOCK"
    return data


def _ensure_itinerary_route_legs(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Fill route gaps between timed package activities using stored addresses."""
    route_days = data.get("route_plan") or []
    if not route_days:
        return route_days
    stay = data.get("stay") or {}
    hotel_address = str(stay.get("hotel_address") or "").strip()
    hotel_name = str(stay.get("room_name") or "酒店").strip()
    public_nodes = data.get("included_public_places") or []
    resource_nodes = [
        row for row in data.get("resources") or []
        if row.get("resource_type") == "PARTNER_RESOURCE" and row.get("start_time")
    ]

    def minutes_of(value: object) -> int | None:
        text = str(value or "")[:5]
        try:
            hour, minute = text.split(":", 1)
            return int(hour) * 60 + int(minute)
        except (TypeError, ValueError):
            return None

    nodes_by_day: dict[int, list[dict[str, Any]]] = {}
    for row in public_nodes:
        if not row.get("included"):
            continue
        node = {
            "title": str(row.get("resource_name") or "").strip(),
            "address": str(row.get("address") or "").strip(),
            "start": minutes_of(row.get("start_time") or row.get("time")),
        }
        if node["title"] and node["start"] is not None:
            nodes_by_day.setdefault(int(row.get("day_index") or 1), []).append(node)
    base_date = str(stay.get("check_in") or data.get("target_date") or "")[:10]
    for row in resource_nodes:
        row_date = str(row.get("available_date") or base_date)[:10]
        day_index = 1
        try:
            from datetime import date
            if base_date and row_date:
                day_index = (date.fromisoformat(row_date) - date.fromisoformat(base_date)).days + 1
        except ValueError:
            pass
        node = {
            "title": str(row.get("resource_name") or "").strip(),
            "address": str(row.get("address") or "").strip(),
            "start": minutes_of(row.get("start_time")),
        }
        if day_index > 0 and node["title"] and node["start"] is not None:
            nodes_by_day.setdefault(day_index, []).append(node)

    def add_leg(legs: list[dict[str, Any]], from_name: str, from_address: str,
                to_name: str, to_address: str) -> None:
        if not from_name or not to_name or from_address == to_address:
            return
        if any(str(leg.get("from_stop") or "") == from_name and str(leg.get("to_stop") or "") == to_name for leg in legs):
            return
        relation = route_proximity(from_address, to_address)
        minutes = relation.get("buffer_minutes")
        if not minutes:
            return
        status = relation.get("status")
        mode = "步行或短途交通" if status in {"same_district", "same_area"} else "打车或公共交通" if status == "cross_district" else "出发前导航核对"
        legs.append({
            "from_stop": from_name,
            "to_stop": to_name,
            "mode": mode,
            "minutes": int(minutes),
            "note": relation.get("reason") or "按地址片区预留转场时间。",
            "distance_label": relation.get("label") or f"约{minutes}分钟转场",
        })

    for day in route_days:
        day_index = int(day.get("day_index") or 1)
        nodes = sorted(nodes_by_day.get(day_index, []), key=lambda node: int(node["start"]))
        if not nodes:
            continue
        legs = day.setdefault("legs", [])
        first = nodes[0]
        add_leg(legs, hotel_name, hotel_address, first["title"], first["address"])
        for previous, following in zip(nodes, nodes[1:]):
            add_leg(legs, previous["title"], previous["address"], following["title"], following["address"])
        last = nodes[-1]
        # Return legs are useful only on days with a stored hotel operation.
        hotel_operation = next((stop for stop in day.get("stops", []) if any(key in str(stop.get("title") or "") for key in ("入住", "退房", "取行李"))), None)
        if hotel_operation:
            add_leg(legs, last["title"], last["address"], str(hotel_operation.get("title") or "返回酒店"), hotel_address)
    return route_days


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
        duration_text = "时长以场次信息为准"
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
        # A nearby museum record must not be attached to a partner activity's
        # booking rules. Public facts are matched by place/address in answer logic.
        source_note = ""
        experience_details.append(
            {
                "name": str(item.get("resource_name") or ""),
                "time": f"{start}–{end}" if start and end else "按当天行程安排",
                "duration": duration_text,
                "address": address,
                "included": "已含在套餐价格内",
                "extra_cost": extra,
                "feature": str(item.get("description") or ""),
                "tips": str(item.get("booking_notice") or "请按产品详情页展示的时间和地址到场。"),
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
    resource_persona_match = True
    room = db.get(RoomInventory, product.room_inventory_id)
    if not room or request.adult_count + request.child_count > room.max_guests:
        children_match = False
    for row, resource in product_partner_rows(db, product):
        if request.weather.upper() not in {"", "UNKNOWN"} and not is_weather_supported(resource.weather_tags, request.weather):
            weather_match = False
        if request.arrival_time and resource.start_time and resource.start_time < request.arrival_time:
            children_match = False
        requested_crowd = str(request.target_crowd or "ALL").upper()
        resource_crowd = product.target_crowd if requested_crowd in {"", "ALL"} else requested_crowd
        # The resource crowd label is a ranking hint; only explicit age limits
        # are a safety gate. Treating a COUPLE/FAMILY label as a hard filter
        # used to erase valid, bookable products from soft family requests.
        if not crowd_supported(resource.suitable_crowds, resource_crowd, [], None, None):
            resource_persona_match = False
        if not crowd_supported(None, "ALL", request.child_ages, resource.minimum_age, resource.maximum_age):
            children_match = False
    # Missing ages require a follow-up before confirming age-restricted
    # experiences, but they do not make every otherwise suitable product an
    # automatic no-match.  The assistant asks for the age in its next turn.
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
    requested_crowd = str(request.target_crowd or "ALL").upper()
    persona_match = requested_crowd in {"", "ALL"} or product.target_crowd in {requested_crowd, "ALL"}
    activity_match = True
    if request.activity_level == "LOW" and any(category in resource_categories for category in {"SPORT", "NATURE", "CITY_WALK"}):
        activity_match = False
    if request.activity_level == "HIGH" and not any(category in resource_categories for category in {"SPORT", "THEME_PARK", "ENTERTAINMENT", "NIGHTLIFE"}):
        activity_match = False
    positive_match = not interest_terms or any(item.lower() in searchable.lower() for item in interest_terms) or bool(requested_categories & semantic_categories)
    # A negative preference only excludes a product that actually contains the
    # unwanted category. It must never make every alternative disappear.
    interest_match = persona_match and resource_persona_match and activity_match and not negative_hit and positive_match
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
        if row.resource_type == "PARTNER_RESOURCE":
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
    near: str = Query(default="", max_length=120, description="当前产品所在片区"),
    limit: int = Query(default=4, ge=1, le=8),
    db: Session = Depends(get_db),
):
    """Recommend verified knowledge-base places, preferring the product area.

    When the knowledge base has too few reviewed entries in the same area, the
    response fills the remaining slots with citywide alternatives. Each field
    is emitted only when it was reviewed; stale or pending records carry an
    explicit caveat and are never presented as bookable package inventory.
    """
    service = KnowledgeService(db)
    search_query = query.strip() or "杭州旅行"
    anchors = area_tokens(near)
    query_terms = [term for term in re.split(r"[\s,，、;；/·|]+", search_query.lower()) if len(term) > 1]
    target_count = min(limit, 8)
    candidates: list[tuple[bool, bool, int, str, dict[str, Any], set[str]]] = []
    for item in service.listing(limit=5000):
        title = str(item.get("name") or "").strip()
        fields = set(item.get("verified_fields") or [])
        status = str(item.get("status") or item.get("verification_status") or "")
        # A title itself must be reviewed, and there must be at least one
        # reviewed location/description field to make the card useful.
        if not title or "name" not in fields or status == "UNAVAILABLE":
            continue
        if not ("address" in fields or "description" in fields):
            continue
        item_areas = area_tokens(item.get("address"), item.get("area"), title)
        same_area = bool(anchors and item_areas & anchors)
        is_remote = bool(anchors and not same_area)
        verified = status == "ACTIVE" and bool(item.get("verified_at"))
        haystack = " ".join(str(item.get(key) or "") for key in ("name", "category_label", "area", "description", "suitable_crowds_label")).lower()
        relevance = sum(2 for term in query_terms if term in haystack)
        candidates.append((is_remote, not verified, -relevance, title, item, fields))

    candidates.sort(key=lambda row: (row[0], row[1], row[2], row[3]))
    guides: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    for is_remote, is_unverified, _, title, item, fields in candidates:
        if title in seen_titles:
            continue
        seen_titles.add(title)
        area = str(item.get("area") or "") if "area" in fields else ""
        address = str(item.get("address") or "") if "address" in fields else ""
        description = re.sub(r"\s+", " ", str(item.get("description") or "")).strip() if "description" in fields else ""
        duration = item.get("suggested_duration_minutes") if "suggested_duration_minutes" in fields else None
        summary_parts = [part for part in (area, f"建议停留 {duration} 分钟" if duration else "") if part]
        distance_note = ""
        if is_remote and anchors:
            distance_note = "这处地点不在当前产品所在片区，可能需要跨区前往；请把交通时间一并安排。"
        guides.append({
            "source": item.get("source_name") or "文旅知识库",
            "title": title,
            "summary": " · ".join(summary_parts),
            "content": description,
            "url": item.get("source_url") or "",
            "address": address,
            "area": area,
            "category_label": item.get("category_label") or item.get("category") or "",
            "crowds_label": item.get("suitable_crowds_label") if "suitable_crowds" in fields else "",
            "best_time": item.get("best_time") if "best_time" in fields else "",
            "transport": item.get("transport") if "transport" in fields else "",
            "duration_minutes": duration,
            "opening_hours": item.get("opening_hours") if "opening_hours" in fields and not is_unverified else "",
            "reservation_notice": item.get("reservation_notice") if "reservation_notice" in fields and not is_unverified else "",
            "verification_status": "VERIFY_REQUIRED" if is_unverified else "ACTIVE",
            "bookable": False,
            "is_remote": is_remote,
            "distance_note": distance_note,
            "verification_note": "地点信息来自文旅知识库；开放时间、预约和票务请出发前再核对。" if is_unverified else "",
        })
        if len(guides) >= target_count:
            break
    return guides


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
    all_items = public_items(db, query, limit=limit, offset=offset, compact=compact)
    cache: dict = build_product_resource_cache(db, all_items)
    populate_room_pool_cache(db, cache, all_items)
    items = [
        visitor_payload(
            db, item, nights=nights, cache=cache,
            include_marketing_assets=not compact, compact=compact,
        )
        for item in all_items
    ]
    # visitor_product_to_dict already clears heavy detail fields when compact=True.
    return items


def _room_pool_remaining(db: Session, hotel_id: int, room_type: str, target_date: date) -> int:
    """Physical room quantity; active intents are already reflected in available_count."""
    pool = db.scalar(select(func.max(RoomInventory.available_count)).where(
        RoomInventory.hotel_id == hotel_id, RoomInventory.room_type == room_type,
        RoomInventory.available_date == target_date))
    return max(0, int(pool or 0))

def same_package_date_options(db: Session, product: TravelProduct) -> list[dict[str, Any]]:
    """Find date-bound products with the same hotel, audience, and paid contents."""
    base_room = db.get(RoomInventory, product.room_inventory_id)
    base_room_type = str(getattr(base_room, "room_type", "") or "")
    cache: dict = {}
    base_payload = visitor_payload(db, product, cache=cache)

    def signature_for(item: TravelProduct, payload: dict[str, Any]) -> tuple:
        entries: list[tuple] = []
        for row in item.resources:
            if row.resource_type == "ROOM":
                continue
            model = HotelService if row.resource_type == "HOTEL_SERVICE" else PartnerResource
            source = db.get(model, row.resource_id)
            start = getattr(source, "start_time", None)
            end = getattr(source, "end_time", None)
            entries.append((
                str(row.resource_type),
                str(row.resource_name or "").strip(),
                int(row.quantity_per_package or 1),
                str(getattr(source, "address", "") or "").strip(),
                start.strftime("%H:%M") if hasattr(start, "strftime") else str(start or "")[:5],
                end.strftime("%H:%M") if hasattr(end, "strftime") else str(end or "")[:5],
            ))
        public_route = tuple(sorted(
            (
                str(stop.get("resource_name") or stop.get("title") or "").strip(),
                str(stop.get("address") or "").strip(),
                str(stop.get("start_time") or stop.get("time") or "").strip(),
                str(stop.get("end_time") or "").strip(),
            )
            for stop in (payload.get("included_public_places") or [])
        ))
        return tuple(sorted(entries)), public_route

    signature = signature_for(product, base_payload)
    best: dict[date, dict[str, Any]] = {}
    for item in list_products(db, public_only=True):
        if item.hotel_id != product.hotel_id or item.theme != product.theme or item.target_crowd != product.target_crowd:
            continue
        room = db.get(RoomInventory, item.room_inventory_id)
        payload = visitor_payload(db, item, cache=cache)
        if signature_for(item, payload) != signature:
            continue
        remaining = int(payload.get("sale_quantity") or 0)
        same_room_type = bool(base_room_type and str(getattr(room, "room_type", "") or "") == base_room_type)
        candidate = {
            "id": item.id,
            "target_date": item.target_date.isoformat(),
            "weekday": "周" + "一二三四五六日"[item.target_date.weekday()],
            "sale_quantity": remaining,
            "status": payload.get("status"),
            "price": str(item.suggested_price),
            "room_type": str(getattr(room, "room_type", "") or ""),
            "theme": item.theme,
            "same_room_type": same_room_type,
        }
        current = best.get(item.target_date)
        if current is None or (same_room_type and not current["same_room_type"]) or (
            same_room_type == current["same_room_type"] and remaining > int(current["sale_quantity"])
        ):
            best[item.target_date] = candidate
    return sorted(best.values(), key=lambda row: row["target_date"])[:20]


def usable_weather_context(db: Session, target_date: date) -> dict[str, Any] | None:
    """Return only a current sourced forecast; stale or failed lookups stay out of advice."""
    try:
        forecast = WeatherService(db).get_forecast("杭州", target_date)
    except Exception:
        return None
    if not forecast.get("usable"):
        return None
    return {
        key: forecast.get(key)
        for key in (
            "city", "target_date", "scenario", "temperature_min", "temperature_max",
            "precipitation_probability", "advisory", "source_name",
        )
        if forecast.get(key) is not None
    }


@router.get("/products/{product_id}/dates")
def product_dates(product_id: int, db: Session = Depends(get_db)):
    """Other departure dates for the same hotel package and paid experiences."""

    product = get_product(db, product_id)
    if not product or not is_publicly_sellable(product):
        raise AppError("NOT_FOUND", "当前套餐不存在或已下架", status_code=404)
    return {"theme": product.theme, "dates": same_package_date_options(db, product)}


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
        remaining = min(max(0, int(product.sale_quantity or 0)),
                         _room_pool_remaining(db, product.hotel_id, room_type, product.target_date))
        options.append(
            {
                "room_inventory_id": room.id,
                "room_type": room_type,
                "max_guests": int(room.max_guests or 0),
                "features": str(room.features or ""),
                "image_url": str(room.image_url or ""),
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
    if room_inventory_id is None and int(product.sale_quantity or 0) > 0:
        base_room = db.get(RoomInventory, product.room_inventory_id)
        base_remaining = min(max(0, int(product.sale_quantity or 0)),
            _room_pool_remaining(db, product.hotel_id, str(getattr(base_room, "room_type", "")), product.target_date)) if base_room else 0
        if base_remaining <= 0:
            choices = db.scalars(select(RoomInventory).where(
                RoomInventory.hotel_id == product.hotel_id,
                RoomInventory.available_date == product.target_date,
                RoomInventory.status == "AVAILABLE", RoomInventory.available_count > 0
            ).order_by(RoomInventory.normal_price)).all()
            selected = next((row for row in choices if min(max(0, int(product.sale_quantity or 0)),
                _room_pool_remaining(db, product.hotel_id, str(row.room_type), product.target_date)) > 0), None)
            if selected:
                room_inventory_id = selected.id
    if room_inventory_id and room_inventory_id != product.room_inventory_id:
        # One package, several room types: swap the room and re-price it.
        room = db.get(RoomInventory, room_inventory_id)
        base_room = db.get(RoomInventory, product.room_inventory_id)
        old_room_name = str(data.get("stay", {}).get("room_name") or "")
        if room and room.hotel_id == product.hotel_id and room.available_date == product.target_date:
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
            remaining = min(max(0, int(product.sale_quantity or 0)),
                             _room_pool_remaining(db, product.hotel_id, str(room.room_type), product.target_date))
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
    data["route_plan"] = _ensure_itinerary_route_legs(data)
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
    budget_target: Decimal | None = None,
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
            key=lambda item: (
                budget_target is not None and item[2].suggested_price <= budget_target,
                item[0],
                (item[2].id * 2654435761 + seed) % 1000003,
            ),
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

    ordered = (
        ranked(scored)
        if budget_target is not None
        else ranked([item for item in scored if item[1]]) + ranked([item for item in scored if not item[1]])
    )
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
    """Opening prompts for the concierge, scoped to the product when selected."""
    current = get_product(db, product_id) if product_id else None
    suggestions: list[str] = []
    greeting = "告诉我日期、同行人、预算或想体验的内容，我会结合天气和当前可售套餐帮你推荐。"
    if current is not None:
        experiences = [row.resource_name for row in current.resources if row.resource_type == "PARTNER_RESOURCE"]
        focus = experiences[0] if experiences else current.theme or current.product_name
        title = current.product_name
        greeting = f"关于「{title}」，告诉我同行人、日期、预算或关心的问题，我会结合这套套餐的权益、行程和可售情况给你建议。"
        suggestions.extend([
            f"「{title}」包含哪些权益？",
            "这套套餐的行程怎么安排？",
            f"{focus}适合哪些人体验？",
            f"{focus}需要预约或准备什么？",
            f"下雨天参加{focus}有什么建议？",
            f"「{title}」还有其他可售日期吗？",
        ])
    else:
        suggestions.extend([
            "预算 700 左右，一家三口有什么推荐？",
            "今天有雨，适合安排什么室内行程？",
            "周末两天，怎么安排杭州亲子行程？",
            "晚上想轻松逛逛，有什么在售套餐？",
            "西湖附近有哪些适合慢游的体验？",
            "第一次来杭州，选哪个套餐更合适？",
        ])
    seen: set[str] = set()
    unique = [item for item in suggestions if item and not (item in seen or seen.add(item))]
    unique = [
        tidy_punctuation(item.rstrip("。，、").rstrip() + "？")
        if not item.rstrip().endswith(("？", "!", "！", "。"))
        else tidy_punctuation(item)
        for item in unique
    ]
    return {"greeting": tidy_punctuation(greeting), "suggestions": unique[:6]}


def _assistant_mode(question: str, has_product_context: bool) -> str:
    """Keep current-product facts scoped until the visitor asks for alternatives."""
    text = re.sub(r"\s+", "", question.strip())
    if not has_product_context:
        return "discovery"
    room_change = re.search(
        r"(?:换|改|切换|选择|查看|看看).{0,6}(?:房型|房间)|(?:其他|别的|可选|可换).{0,5}(?:房型|房间)|房型.{0,8}(?:有哪些|有什么|能换|可换|怎么选)", text,
    )
    if room_change:
        return "room_options"
    package_discovery = re.search(
        r"(?:还有|其他|别的|别款|不同|另一个|其他的|推荐别的|推荐其他).{0,10}(?:套餐|方案|产品|选择)|"
        r"(?:想要|想看|推荐|再推|换成|换个|换一个|换一款).{0,10}(?:套餐|方案|产品|别的|其他|不同)|"
        r"(?:不要|不想要|不喜欢|不考虑|不选).{0,8}(?:这个|当前|这款|本套餐|它)(?:产品|套餐|方案)?|"
        r"(?:不要这个|不要这款|不想要这个|不想要这款|不喜欢这个|不喜欢这款|别推荐这款|换一个|换一款|替代方案|哪个更适合|哪个好|对比|比较一下)", text,
    )
    date_discovery = re.search(r"(?:换|改|选).{0,3}(?:日期|日子|一天)|其他(?:可售)?(?:日期|日子)|别的日期|别的日子|可售日期|哪些日期|哪天.{0,5}(?:可订|可售|有房)|还有.{0,5}(?:日期|日子)", text)
    if package_discovery:
        return "discovery"
    if date_discovery:
        return "date_options"
    if "预算" in text or explicit_budget_amount(text) is not None:
        return "discovery"
    return "product_context"

def _product_question_intent(question: str) -> str:
    """Classify the current turn so product answers stay on the asked topic."""
    text = re.sub(r"\s+", "", str(question or "")).lower()
    if any(term in text for term in ("哪个更适合", "哪个更好", "哪个好", "对比", "比较一下", "有什么区别")):
        return "COMPARISON"
    if any(term in text for term in ("换房", "换房型", "其他房型", "可选房型", "房间有哪些", "房型有哪些", "房间", "房型")):
        return "ROOM"
    if any(term in text for term in ("还剩几", "还有几套", "库存", "余量", "哪天有", "可售日期", "其他日期", "已售罄")):
        return "AVAILABILITY"
    if any(term in text for term in ("需要预约", "怎么预约", "预约吗", "要预约吗", "提前预约", "怎么预订", "如何预订", "怎么买", "购买", "取消", "改期")):
        return "BOOKING"
    if any(term in text for term in ("做什么甜品", "制作什么甜品", "什么甜品", "甜品是什么", "做什么口味", "制作什么", "具体做什么", "材料是否", "材料包含", "烧制", "老师指导", "带回去", "带回家", "带走", "取件", "成品", "作品")):
        return "EXPERIENCE_DETAILS"
    if any(term in text for term in ("多少钱", "价格", "费用", "收费", "预算")):
        return "PRICE"
    if any(term in text for term in ("下雨", "雨天", "天气", "晴天", "会受影响", "室内", "室外", "户外安排")):
        return "WEATHER"
    if any(term in text for term in ("适合", "适不适合", "能不能参加", "可以参加吗", "适龄", "几岁", "年龄", "孩子", "儿童")):
        return "SUITABILITY"
    if any(term in text for term in ("包含", "权益", "套餐有", "有些什么", "有什么内容", "带什么", "几个体验", "体验有哪些")):
        return "INCLUSIONS"
    if any(term in text for term in ("行程", "怎么玩", "怎么安排", "时间表", "先去哪", "路线")):
        return "ITINERARY"
    if any(term in text for term in ("几点", "什么时候", "多久", "多长时间", "体验时间", "活动时间", "开放时间", "几点开门", "几点关门", "闭馆")):
        return "TIME"
    if any(term in text for term in ("地址", "怎么去", "在哪", "位置", "集合地点", "导航")):
        return "LOCATION"
    return "GENERAL"


def _product_context_answer(
    db: Session,
    product: TravelProduct,
    question: str,
    forecast: dict[str, Any] | None = None,
    conversation_context: str = "",
) -> str:
    """Answer product questions from this product's serialized database facts."""
    data = visitor_payload(db, product)
    stay = data.get("stay") or {}
    resources = list(data.get("resources") or [])
    public_stops = list(data.get("included_public_places") or [])
    days = list(data.get("day_plan") or [])
    text = question.strip()
    title = str(data.get("product_name") or product.product_name)
    price = str(data.get("suggested_price") or product.suggested_price)
    room = next((item for item in resources if item.get("resource_type") == "ROOM"), None)
    experiences = [item for item in resources if item.get("resource_type") == "PARTNER_RESOURCE"]
    hotel_services = [item for item in resources if item.get("resource_type") == "HOTEL_SERVICE"]
    room_name = str((room or {}).get("resource_name") or stay.get("room_name") or "酒店住宿")
    nights = int(stay.get("nights") or 1)
    intent = _product_question_intent(text)
    session_text = str(conversation_context or text)[-1000:]
    session_lower = session_text.lower()
    normalized_question = re.sub(r"[\s·•,，。:：|｜/\\-]+", "", text.lower())
    knowledge_service = KnowledgeService(db)
    knowledge_cache: dict[str, dict[str, Any] | None] = {}

    def related_knowledge(item: dict[str, Any]) -> dict[str, Any] | None:
        item_key = str(item.get("id") or item.get("resource_id") or item.get("resource_name") or "")
        if item_key in knowledge_cache:
            return knowledge_cache[item_key]
        name = str(item.get("resource_name") or item.get("title") or "").strip()
        address = str(item.get("address") or "").strip()
        query = " ".join(part for part in (name, address, title, text) if part)
        try:
            rows = knowledge_service.search(
                query,
                target_crowd=str(product.target_crowd or ""),
                weather=str(product.weather or ""),
                limit=12,
            )
        except Exception:  # knowledge improves the answer but never blocks the visitor
            rows = []
        address_key = re.sub(r"[\s·•,，。:：|｜/\\-]+", "", address.lower())
        name_key = re.sub(r"[\s·•,，。:：|｜/\\-]+", "", name.lower())
        ranked: list[tuple[int, dict[str, Any]]] = []
        for row in rows:
            safe = _verified_public_record(row)
            if not safe:
                continue
            fact_address = re.sub(r"[\s·•,，。:：|｜/\\-]+", "", str(safe.get("address") or "").lower())
            fact_name = re.sub(r"[\s·•,，。:：|｜/\\-]+", "", str(safe.get("name") or "").lower())
            fact_copy = re.sub(
                r"[\s·•,，。:：|｜/\\-]+",
                "",
                f"{safe.get('description') or ''}{safe.get('reservation_notice') or ''}".lower(),
            )
            score = 0
            if address_key and fact_address and min(len(address_key), len(fact_address)) >= 8 and (
                address_key in fact_address or fact_address in address_key
            ):
                score += 8
            if fact_name and (fact_name in name_key or fact_name in normalized_question):
                score += 5
            if name_key and name_key in fact_copy:
                score += 4
            shared_terms = [term for term in ("陶艺", "手作", "博物馆", "城市阳台", "湖滨", "运动馆", "甜品") if term in name and term in f"{safe.get('name') or ''}{safe.get('description') or ''}"]
            score += min(4, len(shared_terms) * 2)
            if intent == "LOCATION" and any(term in fact_copy for term in ("公交", "公共交通", "交通线路")):
                score += 4
            if score:
                ranked.append((score, safe))
        result = max(ranked, key=lambda value: value[0])[1] if ranked else None
        knowledge_cache[item_key] = result
        return result

    def question_mentions(item: dict[str, Any]) -> bool:
        name = str(item.get("resource_name") or item.get("title") or "").strip()
        key = re.sub(r"[\s·•,，。:：|｜/\\-]+", "", name.lower())
        if not key:
            return False
        if key in normalized_question:
            return True
        ignored = {"体验", "项目", "内容", "安排", "服务", "地点", "城市", "产品", "套餐", "博物馆"}
        grams = {key[index:index + 2] for index in range(max(0, len(key) - 1))}
        return any(len(term) == 2 and term not in ignored and term in normalized_question for term in grams)

    def selected_experiences() -> list[dict[str, Any]]:
        matched = [item for item in experiences if question_mentions(item)]
        return matched or experiences

    def item_time(item: dict[str, Any]) -> str:
        start = str(item.get("start_time") or "")[:5]
        end = str(item.get("end_time") or "")[:5]
        if start and end:
            return f"{start}–{end}"
        for day in days:
            for entry in day.get("items") or []:
                if str(entry.get("title") or "") == str(item.get("resource_name") or ""):
                    return str(entry.get("time") or "")
        return ""

    date_label = product.target_date.strftime("%m月%d日") if product.target_date else "当前日期"
    stock_copy = f"{date_label}这档售价 ¥{Decimal(str(price)):.2f}/套，当前余 {int(product.sale_quantity or 0)} 套。"

    if intent == "SUITABILITY":
        selected = selected_experiences()
        details: list[str] = []
        for item in selected[:3]:
            name = str(item.get("resource_name") or "套餐体验")
            count = max(1, int(item.get("quantity_per_package") or 1))
            timing = item_time(item)
            description = str(item.get("description") or "").strip()
            suitable_match = re.search(r"适合\s*([^。；;,，]+)", description)
            suitable_text = suitable_match.group(1).strip() if suitable_match else ""
            activity_detail = re.sub(r"[，,；;]?\s*适合[^。；;,，]+", "", description).strip(" 。；;，,")
            if suitable_text:
                lines = [f"{name}更适合{suitable_text}。"]
            elif target_crowd := str(product.target_crowd or "").upper():
                audience = {"COUPLE": "情侣或朋友双人同行", "FAMILY": "亲子家庭", "FRIENDS": "朋友结伴", "SOLO": "独自出行"}.get(target_crowd)
                lines = [f"这款套餐面向{audience}设计；" + (f"{name}的适合人群资料未单独细分。" if audience else f"{name}的适合人群资料暂未细分。")]
            else:
                lines = [f"当前资料没有单独标注{name}的适合人群。"]
            if timing:
                lines.append(f"本套餐安排在 {timing}，每套含 {count} 份。")
            if activity_detail:
                lines.append(f"体验内容：{activity_detail}。")
            if any(term in session_lower for term in ("情侣", "恋人", "夫妻")):
                lines.append("你前面提到情侣同行，这项双人协作体验与两人一起制作的形式相符。")
            elif any(term in session_lower for term in ("朋友同行", "朋友一起", "和朋友", "好友")):
                lines.append("你前面提到和朋友同行，这项体验可以由两人一起参与。")
            rain_context = any(term in session_lower for term in ("下雨", "雨天", "有雨", "可能下雨", "阵雨"))
            indoor_evidence = item.get("indoor") is True or any(term in description for term in ("室内", "工作室"))
            if indoor_evidence and (rain_context or str(product.weather or "").upper() == "RAIN"):
                if rain_context:
                    lines.append("你前面提到可能下雨；这项安排在工作室内，适合作为雨天的室内体验。")
                else:
                    lines.append("这项安排在室内工作室，雨天时可作为当天的室内体验。")
            elif item.get("indoor") is False and rain_context:
                lines.append("你提到可能遇雨；这项体验登记为户外活动，建议出发前联系体验方确认是否照常进行。")
            details.append("".join(lines))
        target = {"COUPLE": "双人同行", "FAMILY": "亲子家庭", "FRIENDS": "朋友同行", "SOLO": "独自出行"}.get(str(product.target_crowd or "").upper(), "")
        answer = " ".join(details)
        itinerary_names = list(dict.fromkeys(
            str(item.get("resource_name") or item.get("title") or "").strip()
            for item in public_stops
            if str(item.get("resource_name") or item.get("title") or "").strip()
        ))
        if room or itinerary_names:
            context_parts = []
            if room:
                context_parts.append(f"{room_name}住 {nights} 晚")
            if itinerary_names:
                context_parts.append("正式行程还包括" + "、".join(itinerary_names[:3]))
            answer += "整套安排中" + "，".join(context_parts) + (f"，整体按{target}的节奏设计。" if target else "。")
        if any(word in session_lower for word in ("孩子", "小孩", "儿童", "几岁", "年龄")):
            ages = re.findall(r"(?<!\d)(\d{1,2})\s*岁", session_text)
            child_copy = f"你前面提到 {ages[-1]} 岁孩子；" if ages else "如果有儿童同行，"
            limits = []
            for item in selected[:3]:
                minimum, maximum = item.get("minimum_age"), item.get("maximum_age")
                if minimum is not None or maximum is not None:
                    limits.append(f"{item.get('resource_name')}要求 {minimum if minimum is not None else '不限'}–{maximum if maximum is not None else '不限'} 岁")
            if limits:
                answer += child_copy + "已登记的年龄条件为：" + "；".join(limits) + "。"
            else:
                answer += child_copy + "当前产品资料没有列出这项课程的年龄限制，建议购买前向体验方确认儿童接待要求。"
        return answer

    if intent == "AVAILABILITY":
        capacity = int(stay.get("max_guests") or (room or {}).get("max_guests") or 0)
        room_copy = f"当前房型为{room_name}，最多入住 {capacity} 人。" if capacity else ""
        return f"「{title}」{date_label}场次：¥{Decimal(str(price)):.2f}/套，余 {int(product.sale_quantity or 0)} 套。{room_copy}"

    if intent == "TIME" and any(word in text for word in ("开放时间", "几点开门", "几点关门", "闭馆", "什么时候开放")):
        selected = [item for item in [*experiences, *public_stops] if question_mentions(item)] or [*experiences, *public_stops]
        details = []
        for item in selected[:3]:
            fact = related_knowledge(item)
            if not fact:
                continue
            name = str(item.get("resource_name") or item.get("title") or fact.get("name") or "场馆")
            opening = str(fact.get("opening_hours") or "").strip()
            timing = item_time(item)
            if opening:
                details.append(f"{name}的场馆日常开放时间为{opening}")
            if timing:
                details.append(f"当前套餐为该地点安排的正式体验/行程时段是{timing}，应按套餐场次区分于日常参观时间")
        return "；".join(details) + "。" if details else f"知识库暂时没有匹配到相关地点的开放时段；我不会用场馆常规开放时间替代套餐场次。"

    if intent == "INCLUSIONS":
        included = [f"{room_name} 1 间，住 {nights} 晚"] if room else [f"住宿 {nights} 晚"]
        included.extend(f"{item.get('resource_name')} × {max(1, int(item.get('quantity_per_package') or 1))} 份" for item in experiences)
        included.extend(str(item.get("resource_name") or "") for item in hotel_services)
        formal = [item for item in public_stops if str(item.get("resource_name") or item.get("title") or "").strip()]
        paragraphs = ["这套套餐包含" + "、".join(value for value in included if value) + "。"]
        for item in experiences[:4]:
            name = str(item.get("resource_name") or "这项体验")
            description = visitor_answer_copy(item.get("description") or "")
            if description:
                paragraphs.append(f"{name}：{description}")
        if formal:
            places = [str(item.get("resource_name") or item.get("title") or "").strip() for item in formal]
            paragraphs.append("行程还正式安排了" + "、".join(name for name in places if name) + "；这些公共行程已纳入套餐安排，无需另购门票。")
        if hotel_services:
            paragraphs.append("酒店服务包括" + "、".join(str(item.get("resource_name")) for item in hotel_services if item.get("resource_name")) + "。")
        return "\n\n".join(paragraphs[:5])

    if intent == "EXPERIENCE_DETAILS":
        selected = [item for item in experiences if question_mentions(item)] or experiences
        paragraphs = []
        dessert_question = any(term in text for term in ("甜品", "甜点", "糕点"))
        for item in selected[:2]:
            name = str(item.get("resource_name") or "这项体验")
            count = max(1, int(item.get("quantity_per_package") or 1))
            description = visitor_answer_copy(str(item.get("description") or "").strip())
            booking_notice = visitor_answer_copy(str(item.get("booking_notice") or "").strip())
            timing = item_time(item)
            if dessert_question and "甜品" in name:
                line = f"这套包含 {count} 人份的{name}，从食材准备、动手制作和造型到成品品尝，材料与老师指导已包含在体验中。"
                if "桂花" in description:
                    line += "口味按当天课程安排；商品资料没有列出固定甜品名称，因此不能承诺指定某一种。"
            elif description:
                line = f"{name}：{description}"
            else:
                line = f"这套安排了{name}，商品资料没有进一步写明你问的细节；目前能确认的是它列在套餐体验中。"
            if timing and any(term in text for term in ("几点", "时间", "多久", "什么时候")):
                line += f"体验时段为 {timing}。"
            if booking_notice and any(term in text for term in ("预约", "到场", "报名")):
                line += f"{booking_notice}"
            paragraphs.append(line)
        return "\n\n".join(paragraphs) if paragraphs else "当前商品列出的体验中没有匹配到这个项目；页面明确包含的体验以商品权益卡片为准。"

    if intent == "ITINERARY":
        day_count = len([day for day in days if day.get("items")])
        duration = f"{day_count} 天 {nights} 晚" if day_count else f"{nights + 1} 天 {nights} 晚"
        crowd = "双人" if str(product.target_crowd or "").upper() == "COUPLE" else "亲子" if str(product.target_crowd or "").upper() == "FAMILY" else ""
        paragraphs = [f"这是一趟{duration}的{crowd}行程，安排了城市漫步、套餐体验和住宿衔接；公共开放地点只要列入下方行程，也属于正式套餐内容。"]
        def sort_time(value: str) -> int:
            match = re.search(r"(\d{1,2}):(\d{2})", value or "")
            return int(match.group(1)) * 60 + int(match.group(2)) if match else 9999
        for day in days:
            day_index = int(day.get("day_index") or 0)
            entries: list[tuple[int, str]] = []
            for item in day.get("items") or []:
                name = str(item.get("title") or "").strip()
                if not name:
                    continue
                when = str(item.get("time") or "").strip()
                kind = str(item.get("kind") or "")
                desc = visitor_answer_copy(str(item.get("description") or "").strip())
                duration_text = str(item.get("duration_text") or "").strip()
                line = f"{when}安排{name}" if when else name
                if duration_text and duration_text not in when:
                    line += f"（{duration_text}）"
                if kind == "PARTNER_RESOURCE" and desc:
                    line += f"，{desc}"
                elif kind in {"ROOM", "BAGGAGE"} and desc:
                    line += f"，{desc}"
                if name == "午餐与转场":
                    line += "，用餐和前往下一站的交通自行安排"
                elif name == "早餐与整理行李":
                    line += "，早餐后整理行李，再继续当天路线"
                entries.append((sort_time(when), line))
            for stop in public_stops:
                if int(stop.get("day_index") or 0) != day_index:
                    continue
                name = str(stop.get("resource_name") or stop.get("title") or "").strip()
                if not name:
                    continue
                when = str(stop.get("time") or "").strip()
                duration_text = str(stop.get("duration_text") or "").strip()
                desc = visitor_answer_copy(str(stop.get("description") or "").strip())
                line = f"{when}安排{name}" if when else name
                if duration_text:
                    line += f"（{duration_text}）"
                if desc:
                    line += f"，{desc}"
                entries.append((sort_time(when), line))
            entries.sort(key=lambda row: row[0])
            if entries:
                label = str(day.get("label") or f"第 {day_index} 天").strip()
                paragraphs.append(label + "：" + "；".join(line for _, line in entries) + "。")
        if len(paragraphs) == 1:
            names = [str(item.get("resource_name") or "") for item in experiences if item.get("resource_name")]
            paragraphs.append("目前明确安排的体验包括" + "、".join(names[:3]) + "；各项时间以详情页行程表为准。")
        if hotel_services:
            paragraphs.append("酒店行李寄存服务可衔接早到和退房后的游玩安排。")
        return "\n\n".join(paragraphs[:5])

    if intent == "BOOKING":
        selected = [item for item in experiences if question_mentions(item)] or experiences
        details = []
        for item in selected[:3]:
            name = str(item.get("resource_name") or "体验")
            timing = item_time(item)
            notice = visitor_answer_copy(str(item.get("booking_notice") or "").strip())
            low_age, high_age = item.get("minimum_age"), item.get("maximum_age")
            line = name + (f"列出的体验时段是 {timing}" if timing else "")
            line += f"；商品须知：{notice}" if notice else "；商品没有注明是否需要额外预约，购买时请按可售场次和订单说明安排"
            if low_age is not None or high_age is not None:
                low = f"{low_age} 周岁" if low_age is not None else "不限"
                high = f"{high_age} 周岁" if high_age is not None else "以上"
                line += f"；适用年龄为 {low}至{high}"
            details.append(line + "。")
        return "\n\n".join(details) if details else "这款商品列出了体验场次，但没有写明是否需要额外预约；下单时以可售日期和订单中的场次信息为准。"

    if intent == "LOCATION":
        details = []
        selected = [item for item in [*experiences, *hotel_services, *public_stops] if question_mentions(item)] or [*experiences, *hotel_services, *public_stops]
        for item in selected[:4]:
            name = str(item.get("resource_name") or "体验")
            timing = item_time(item)
            address = str(item.get("address") or "").strip()
            notice = str(item.get("booking_notice") or "").strip()
            fact = related_knowledge(item)
            detail = name
            if timing:
                detail += f" {timing}"
            if address:
                detail += f"，地址：{address}"
            if intent == "BOOKING" and notice:
                detail += f"；{notice}"
            minimum_age, maximum_age = item.get("minimum_age"), item.get("maximum_age")
            if intent == "BOOKING" and (minimum_age is not None or maximum_age is not None):
                low = f"{minimum_age}周岁" if minimum_age is not None else "不限"
                high = f"{maximum_age}周岁" if maximum_age is not None else "以上"
                detail += f"；适用年龄 {low}–{high}"
            if fact and address:
                fact_address = re.sub(r"[\s·•,，。:：|｜/\\-]+", "", str(fact.get("address") or "").lower())
                item_address = re.sub(r"[\s·•,，。:：|｜/\\-]+", "", address.lower())
                same_venue = bool(fact_address and len(fact_address) >= 8 and fact_address in item_address)
                venue_question = any(term in text for term in ("博物馆", "场馆", "入馆", "参观", "门票"))
                if intent == "BOOKING" and same_venue and venue_question:
                    reservation = str(fact.get("reservation_notice") or "").strip()
                    if reservation:
                        detail += f"；场馆参观：{reservation}（与套餐内体验报名分开办理）"
                if intent == "LOCATION" and same_venue:
                    description = str(fact.get("description") or "")
                    transit = re.search(r"(?:公交|公共交通|交通线路)[：:]?([^。；;]+)", description)
                    transport = str(fact.get("transport") or (transit.group(0) if transit else "")).strip()
                    if transport:
                        detail += f"；怎么去：{transport}"
            details.append(detail)
        return "\n\n".join(details) if details else "当前产品资料没有提供对应地点的集合地址；行程中展示的是已安排的体验地点。"

    if intent == "WEATHER":
        indoor: list[str] = []
        outdoor: list[str] = []
        for item in experiences:
            resource = db.get(PartnerResource, int(item.get("resource_id") or 0)) if item.get("resource_id") else None
            name = str(item.get("resource_name") or "套餐体验")
            if resource is not None and bool(resource.indoor):
                indoor.append(name)
            elif resource is not None:
                outdoor.append(name)
        for item in public_stops:
            name = str(item.get("resource_name") or item.get("title") or "").strip()
            clue = name + str(item.get("description") or "")
            if any(term in clue for term in ("步行街", "城市阳台", "湖滨", "西湖水岸", "沿江", "公园", "湖岸")):
                outdoor.append(name)
            elif any(term in clue for term in ("博物馆", "美术馆", "科技馆", "展馆")):
                indoor.append(name)
        indoor = list(dict.fromkeys(indoor)); outdoor = list(dict.fromkeys(outdoor))
        parts: list[str] = []
        if indoor:
            focus = next((item for item in experiences if question_mentions(item) and str(item.get("resource_name") or "") in indoor), None)
            parts.append(f"雨天可以保留室内安排：{'、'.join(indoor[:3])}" + (f"，其中{focus.get('resource_name')}在 {item_time(focus)}，体验本身不依赖户外天气。" if focus and item_time(focus) else "，适合作为当天的主要活动。"))
        if outdoor:
            parts.append(f"需要看雨势调整的是{'、'.join(outdoor[:3])}，它们属于户外漫步；雨大时可以缩短停留或跳过，不建议把它们当作室内体验。")
        if indoor and outdoor:
            parts.append("所以这套属于“室内主体验 + 户外路线”的部分适雨安排：优先保留室内体验，再按现场雨势决定是否走公共路线；跨区移动也记得预留交通时间。")
        elif indoor:
            parts.append("这套目前能确认的安排以室内项目为主，出发前再查看当天的场次信息即可。")
        elif outdoor:
            parts.append(f"这款正式安排主要是户外内容（{'、'.join(outdoor[:3])}）；如果希望基本不淋雨，室内手作或展馆类套餐会更合适。")
        else:
            parts.append("这款商品没有足够信息判断全部项目的室内外属性；我不会仅凭产品名称把它判成雨天友好。")
        asks_forecast = bool(re.search(r"预报|气温|降雨概率|天气怎么样|天气如何|明天什么天气", text))
        if forecast and asks_forecast:
            parts.append(f"{forecast.get('target_date')}杭州天气：{forecast.get('advisory')}。")
        return "\n\n".join(parts)

    if intent == "PRICE":
        parts = [f"当前售价 ¥{price}/套，包含{room_name} {nights} 晚"]
        if experiences:
            parts.append("包含体验：" + "、".join(str(item.get("resource_name")) for item in experiences))
        if hotel_services:
            parts.append("酒店服务：" + "、".join(str(item.get("resource_name")) for item in hotel_services))
        if public_stops:
            parts.append("正式公共行程无需另付门票")
        return "；".join(parts) + "。" + stock_copy

    if intent == "TIME":
        selected = [item for item in [*experiences, *public_stops] if question_mentions(item)] or [*experiences, *public_stops]
        times = []
        for item in selected[:3]:
            timing = item_time(item)
            if timing:
                name = str(item.get("resource_name") or item.get("title") or "行程地点")
                times.append(f"{name}安排在 {timing}")
        return "；".join(times) + "。" if times else "套餐资料中没有这项活动的具体开始时间，建议按产品页集合安排与酒店确认信息为准。"

    if intent == "ROOM":
        capacity = stay.get("max_guests") or (room or {}).get("max_guests") or "以房型资料为准"
        features = str((room or {}).get("description") or "").strip()
        return f"当前选择的是{room_name}，最多入住 {capacity} 人。{features if features else '同日其他可售房型和价格可在商品首屏的房型卡中切换查看。'}"

    relevant_names = [
        str(item.get("resource_name") or "").strip()
        for item in [*experiences, *hotel_services, *public_stops]
        if str(item.get("resource_name") or "").strip()
    ]
    named_items = "、".join(relevant_names[:3]) or room_name
    return f"这款套餐安排了{named_items}。商品页没有写到你问的细节，我不替酒店或体验方补充承诺；如果你指的是预约、年龄或材料等某一项，我可以继续按该体验核对。"


def _product_context_followups(
    question: str,
    product: TravelProduct,
    conversation_context: str = "",
) -> list[str]:
    """Offer two next questions that naturally continue this product topic."""
    intent = _product_question_intent(question)
    resources = list(getattr(product, "resources", []) or [])
    experience = next((row.resource_name for row in resources if row.resource_type == "PARTNER_RESOURCE"), "这项体验")
    if intent == "SUITABILITY":
        context = f"{question} {conversation_context}".lower()
        suggestions = []
        if not any(term in context for term in ("下雨", "雨天", "有雨", "阵雨")):
            suggestions.append("下雨天体验会受影响吗？")
        if not any(term in context for term in ("孩子", "小孩", "儿童", "几岁", "年龄")):
            suggestions.append("儿童可以参加吗？")
        if not any(term in context for term in ("预约", "预订")):
            suggestions.append(f"{experience}需要提前预约吗？")
        if len(suggestions) < 2:
            suggestions.extend(["这套产品的行程怎么安排？", "还有其他可售日期吗？"])
        return suggestions[:2]
    if intent == "PRICE":
        return ["套餐具体包含哪些内容？", "还有其他可售日期吗？"]
    if intent == "INCLUSIONS":
        return ["这套产品的行程怎么安排？", "哪些体验需要提前预约？"]
    if intent in {"ITINERARY", "TIME"}:
        return ["体验集合地址在哪里？", "下雨天哪些安排在室内？"]
    if intent == "LOCATION":
        return [f"{experience}需要提前预约吗？", "这趟行程还包含哪些体验？"]
    if intent == "BOOKING":
        return ["提交购买意向后如何确认？", "还有其他可售日期吗？"]
    if intent == "WEATHER":
        return ["这套产品的完整行程是什么？", f"{experience}的集合地址在哪里？"]
    if intent == "AVAILABILITY":
        return ["同一天还有其他房型吗？", "这个套餐还包含哪些体验？"]
    if intent == "ROOM":
        return ["还有其他可售日期吗？", "当前套餐包含哪些体验？"]
    return [f"{experience}适合哪些人体验？", "这套产品的行程怎么安排？"]


def assistant_date_alternatives(db: Session, product: TravelProduct) -> tuple[str, list[dict[str, Any]], dict[str, str], list[dict[str, Any]]]:
    """Search same-package dates first, then nearby same-day/date alternatives."""
    inventory_cache: dict[str, Any] = {}
    live = [
        item for item in list_products(db, public_only=True)
        if item.id != product.id and item.status in {"ON_SALE", "LOW_STOCK"}
        and int(item.sale_quantity or 0) > 0 and is_publicly_sellable(item)
        and item.target_date >= date.today()
        and package_room_remaining(db, item, inventory_cache) > 0
    ]
    by_id = {item.id: item for item in live}
    dates = [
        row for row in same_package_date_options(db, product)
        if row["target_date"] != product.target_date.isoformat()
        and int(row.get("sale_quantity") or 0) > 0 and row["id"] in by_id
    ]
    dates.sort(key=lambda row: abs((date.fromisoformat(row["target_date"]) - product.target_date).days))
    chosen = [by_id[row["id"]] for row in dates[:3]]
    exact = bool(chosen)
    if not chosen:
        base_text = " ".join([str(product.theme or ""), *(str(row.resource_name or "") for row in product.resources if row.resource_type != "ROOM")]).lower()
        terms = [term for term in ("西湖", "湖滨", "夜游", "夜景", "陶艺", "手作", "城市阳台", "运动", "亲子", "甜品", "博物馆", "钱江") if term in base_text]
        base_areas = product_area_tokens(db, product)
        ranked = []
        for item in live:
            days = abs((item.target_date - product.target_date).days)
            if days > 14:
                continue
            text = " ".join([str(item.theme or ""), str(item.product_name or ""), *(str(row.resource_name or "") for row in item.resources if row.resource_type != "ROOM")]).lower()
            same_theme = str(item.theme or "").strip().lower() == str(product.theme or "").strip().lower()
            same_crowd = item.target_crowd == product.target_crowd
            shared_terms = sum(term in text for term in terms)
            shared_areas = len(base_areas & product_area_tokens(db, item))
            same_day_room = item.target_date == product.target_date and item.hotel_id == product.hotel_id and same_theme and same_crowd
            if not (same_day_room or same_theme or shared_terms or (shared_areas and same_crowd)):
                continue
            rank = (0 if same_day_room else 1 if days <= 7 else 2, 0 if same_theme else 1, -shared_terms-shared_areas, abs(Decimal(str(item.suggested_price or 0))-Decimal(str(product.suggested_price or 0))))
            ranked.append((rank, item))
        ranked.sort(key=lambda pair: pair[0])
        chosen = [item for _, item in ranked[:3]]
    cache: dict[str, Any] = {}
    cards = [visitor_payload(db, item, cache=cache) for item in chosen]
    reasons: dict[str, str] = {}
    for item, card in zip(chosen, cards):
        amount = Decimal(str(item.suggested_price or 0))
        delta = amount - Decimal(str(product.suggested_price or 0))
        price = "价格相同" if not delta else f"价格{'高' if delta > 0 else '低'} ¥{abs(delta):.2f}"
        names = [row.resource_name for row in item.resources if row.resource_type != "ROOM" and row.resource_name]
        shared = [name for name in names if any(name == row.resource_name for row in product.resources)]
        kept = "、".join(shared[:2]) or ("同主题体验" if item.theme == product.theme else "相近地点与客群")
        reasons[str(item.id)] = f"{item.target_date.month}月{item.target_date.day}日可订，保留{kept}；{price}，余 {int(card.get('sale_quantity') or 0)} 套。"
    date_cards = [dict(row) for row in dates[:3]]
    if chosen and exact:
        answer = f"这款还有 {len(chosen)} 个其他日期可订，下面按离 {product.target_date.month}月{product.target_date.day}日最近的顺序列出，同套餐权益保持一致。"
    elif chosen:
        answer = f"这款当前可售日期是 {product.target_date.month}月{product.target_date.day}日。我继续查了同日房型和前后14天相近套餐，优先保留主题、同行人群或地点；下面每张卡都说明了与当前款的差异。"
    else:
        answer = f"当前在售数据中只查到「{product.product_name}」{product.target_date.month}月{product.target_date.day}日这一档；同套餐日期、同日房型和前后14天的相近套餐目前都没有可用库存。"
    return answer, cards, reasons, date_cards


@router.post("/consult")
def consult(request: VisitorQuestion, db: Session = Depends(get_db)):
    if sweep_expired_intents(db):
        db.commit()
    assistant_mode = _assistant_mode(request.question, request.product_id is not None)
    product = get_product(db, request.product_id) if request.product_id else None
    if product and (product.status not in {"ON_SALE", "LOW_STOCK"} or (product.sale_quantity <= 0 and assistant_mode == "discovery")):
        product = None
    if request.product_id is not None and assistant_mode == "product_context":
        if product is None:
            return {"mode": "product_context", "answer": "暂时无法读取这套产品的当前资料，请返回商品页重新打开后再问。", "product_id": request.product_id, "product": None, "suggestions": [], "room_options": []}
        forecast = usable_weather_context(db, product.target_date) if any(word in request.question for word in ("下雨", "天气", "雨天", "晴天")) else None
        answer = visitor_answer_copy(_product_context_answer(db, product, request.question, forecast, request.natural_language))
        return {"mode": "product_context", "answer": answer, "product_id": product.id, "product": None, "suggestions": [], "room_options": [], "follow_up_questions": _product_context_followups(request.question, product, request.natural_language)}
    if request.product_id is not None and assistant_mode == "date_options":
        if product is None:
            return {"mode": "date_options", "answer": "暂时无法读取这套产品的可售日期，请返回商品页重新打开后再试。", "product_id": request.product_id, "product": None, "suggestions": [], "room_options": [], "date_options": []}
        answer, suggestions, reasons, date_options = assistant_date_alternatives(db, product)
        return {"mode": "date_options", "answer": answer, "product_id": product.id,
                "product": None, "suggestions": suggestions, "reasons": reasons,
                "room_options": [], "date_options": date_options,
                "follow_up_questions": ["同一天还有其他房型吗？", "这些套餐的体验内容有什么不同？"]}
    if request.product_id is not None and assistant_mode == "room_options" and product is None:
        return {"mode": "product_context", "answer": "暂时无法读取这套产品的房型信息，请返回商品页重新打开后再试。", "product_id": request.product_id, "product": None, "suggestions": [], "room_options": []}
    conversation_text = (request.natural_language or request.question).strip()[-1000:]
    interpreted_request, _ = enrich_recommend_request(VisitorRecommendRequest(natural_language=conversation_text, weather=request.weather, target_crowd="ALL"))
    asks_for_alternatives = assistant_mode == "discovery"
    explicitly_avoids_current_product = bool(re.search(
        r"(?:不要|不想要|别推荐|排除|不考虑).{0,10}(?:当前|现在|这个|这款|本产品|本套餐|正在看的)",
        conversation_text,
    ))
    visible_products = list_products(db, public_only=True)
    payload = {
        "question": request.question,
        "natural_language": conversation_text,
        "weather": request.weather,
        "target_crowd": interpreted_request.target_crowd,
        "negative_interests": interpreted_request.negative_interests,
        "activity_level": interpreted_request.activity_level,
        "products": [safe_product_context(db, item) for item in (visible_products if asks_for_alternatives else ([product] if product else visible_products))],
        "allergy_information": "",
    }
    # 让回答能结合「要什么/不要什么」和知识库里的地点资料，而不是只做关键词匹配。
    try:
        payload["knowledge"] = [
            {key: value for key, value in safe.items() if key not in {"source_url", "verification_status", "verified_at"}}
            for record in KnowledgeService(db).search(conversation_text, limit=12)
            if (safe := _verified_public_record(record)) is not None
        ][:4]
        payload["tourism_reference_context"] = strip_reference_metadata(
            curated_tourism_context(conversation_text, db)
        )
    except Exception:  # knowledge is optional context, never block the answer
        payload["knowledge"] = []
        payload["tourism_reference_context"] = strip_reference_metadata(
            curated_tourism_context(conversation_text, db)
        )
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
            remaining = min(max(0, int(product.sale_quantity or 0)),
                            _room_pool_remaining(db, product.hotel_id, room_type, product.target_date))
            delta = Decimal(str(room.normal_price or 0)) - base_normal
            room_options.append(
                {
                    "room_inventory_id": room.id,
                    "room_type": room_type,
                    "max_guests": int(room.max_guests or 0),
                    "features": str(room.features or ""),
                    "image_url": str(room.image_url or ""),
                    "price": str((Decimal(str(product.suggested_price)) + delta).quantize(Decimal("0.01"))),
                    "remaining": remaining,
                    "is_current": room.id == product.room_inventory_id,
                }
            )
        payload["room_options"] = room_options
        if assistant_mode == "room_options":
            requested_party_size = int(interpreted_request.adult_count or 0) + int(interpreted_request.child_count or 0)
            requested_budget = explicit_budget_amount(conversation_text)
            room_price_limit = budget_search_ceiling(conversation_text, requested_budget) if requested_budget is not None else None
            room_options = [
                item for item in room_options
                if int(item.get("remaining") or 0) > 0
                and (not requested_party_size or not int(item.get("max_guests") or 0)
                    or int(item.get("max_guests") or 0) >= requested_party_size)
                and (room_price_limit is None or Decimal(str(item.get("price") or "0")) <= room_price_limit)
            ]
            payload["room_options"] = room_options
            available = [item for item in room_options if not item["is_current"]]
            answer = (
                "同一套餐当天可选房型如下，点击房型卡即可查看该房型的价格与行程。"
                if available
                else "当前日期没有其他可售房型，可以查看其他可售日期或套餐。"
            )
            return {"mode": "room_options", "answer": answer, "product_id": product.id, "product": None, "suggestions": [], "room_options": room_options}
    try:
        result = AgentOrchestrator(db, hotel_id=product.hotel_id if product else None, source_channel="WEB_VISITOR", actor_role="VISITOR", conversation_id=request.conversation_id).match_visitor(payload)
        # Visitor-match telemetry is redacted by the orchestrator; persist the
        # diagnostic row independently of any later response serialization.
        db.commit()
        raw_answer = visitor_answer_copy(getattr(result.value, "answer", ""))
    except AppError as exc:
        if exc.code != "AGENT_UNAVAILABLE":
            raise
        # Keep discovery usable when OpenClaw times out or returns invalid JSON.
        # Candidates and facts below are still computed from live DB inventory.
        raw_answer = ""
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
    context_date = product.target_date if product else None
    explicit_target_date = explicit_calendar_date(conversation_text, context_date)
    effective = VisitorRecommendRequest(
        natural_language=conversation_text,
        weather=request.weather,
        budget=Decimal("2000"),
        # A product's date is context, not a hidden constraint on a general
        # alternatives request. Keep it only for questions about that product.
        target_date=explicit_target_date or (None if asks_for_alternatives else context_date),
        # The current package is context, not a hard audience filter.  A
        # visitor can ask for a couple, a family or friends from any detail.
        target_crowd="ALL",
    )
    effective, _ = enrich_recommend_request(effective)
    weather_date = effective.target_date or (context_date if not asks_for_alternatives else None)
    weather_context = usable_weather_context(db, weather_date) if weather_date else None
    explicit_weather_preference = bool(re.search(r"雨|下雨|湿冷|晴|多云|阴天", conversation_text))
    if weather_context and str(effective.weather or "UNKNOWN").upper() == "UNKNOWN":
        effective = effective.model_copy(update={"weather": str(weather_context.get("scenario") or "UNKNOWN")})
    payload["weather"] = str(effective.weather or "UNKNOWN")
    payload["weather_preference"] = str(effective.weather or "UNKNOWN") if explicit_weather_preference else ""
    if weather_context:
        payload["weather_context"] = weather_context
    else:
        payload.pop("weather_context", None)
    budget_explicit = explicit_budget_amount(conversation_text) is not None
    budget_hard_limit = hard_budget_limit(conversation_text)
    budget_ceiling = budget_search_ceiling(conversation_text, effective.budget) if budget_explicit else effective.budget
    payload["budget"] = str(effective.budget) if budget_explicit else ""
    payload["budget_search_ceiling"] = str(budget_ceiling) if budget_explicit else ""
    payload["budget_policy"] = "HARD_MAX" if budget_hard_limit else "TARGET_WITH_SMALL_TRADEOFF" if budget_explicit else "FLEXIBLE"
    if budget_explicit and product is not None:
        payload["room_options"] = [
            option for option in (payload.get("room_options") or [])
            if Decimal(str(option.get("price") or "0")) <= budget_ceiling
            and int(option.get("remaining") or 0) > 0
            and (not (int(effective.adult_count or 0) + int(effective.child_count or 0))
                or not int(option.get("max_guests") or 0)
                or int(option.get("max_guests") or 0) >= int(effective.adult_count or 0) + int(effective.child_count or 0))
        ]
    elif product is not None:
        requested_party_size = int(effective.adult_count or 0) + int(effective.child_count or 0)
        if requested_party_size:
            payload["room_options"] = [
                option for option in (payload.get("room_options") or [])
                if not int(option.get("max_guests") or 0)
                or int(option.get("max_guests") or 0) >= requested_party_size
            ]
    requested_terms = [*effective.interests, *effective.requested_places]
    display_terms = display_preference_terms(requested_terms)
    requested_categories = preference_categories(" ".join(str(term) for term in requested_terms))
    # Prefer experiences that sit in the same part of the city as whatever the
    # traveller named (or as the product they are currently reading).
    target_areas: set[str] = set()
    for term in requested_terms:
        target_areas |= area_tokens(term)
    if product is not None and not asks_for_alternatives:
        target_areas |= product_area_tokens(db, product)
    scored: list[tuple[int, bool, TravelProduct]] = []
    weather_relaxed: list[tuple[int, bool, TravelProduct]] = []
    assistant_inventory_cache: dict[str, Any] = {}
    party_size = int(effective.adult_count or 0) + int(effective.child_count or 0)
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
        child_ok, weather_ok, interest_ok, score, negative_hit = matches_conditions(db, item, effective)
        if negative_hit:
            continue
        # A solo-only product is not a sensible recommendation for a family
        # or other multi-person party, even when its room capacity is larger.
        if party_size > 1 and str(item.target_crowd or "").upper() == "SOLO":
            continue
        if item.sale_quantity <= 0 or not child_ok or not is_publicly_sellable(item):
            continue
        room = db.get(RoomInventory, item.room_inventory_id) if item.room_inventory_id else None
        room_capacity = int(room.max_guests or 0) if room else 0
        if party_size and room_capacity and party_size > room_capacity:
            continue
        room = db.get(RoomInventory, item.room_inventory_id) if item.room_inventory_id else None
        room_capacity = int(room.max_guests or 0) if room else 0
        if party_size and room_capacity and party_size > room_capacity:
            continue
        if package_room_remaining(db, item, assistant_inventory_cache) <= 0:
            continue
        if budget_explicit and item.suggested_price > budget_ceiling:
            continue
        if item.target_crowd == effective.target_crowd:
            score += 8
        elif effective.target_crowd not in {"", "ALL"} and item.target_crowd not in {"", "ALL", effective.target_crowd}:
            # Keep cross-audience products available as a comparison when
            # their real capacity and experience still fit, but rank them well
            # below options designed for the requested party.
            score -= 18 if effective.target_crowd in {"FAMILY", "COUPLE", "FRIENDS"} else 10
        if effective.target_date and item.target_date == effective.target_date:
            score += 10
        if budget_explicit:
            # Explicit budget is a primary decision factor. Keep modestly over-target
            # options available for comparison, but rank in-budget packages first.
            if item.suggested_price <= effective.budget:
                score += 22
            else:
                score -= 24
        elif item.suggested_price <= effective.budget:
            score += 7
        else:
            score -= min(8, int((item.suggested_price - effective.budget) / Decimal("200")) + 1)
        score += hits * 28
        score += title_hits * 20
        # Positive themes, crowd labels and weather tags rank options; only
        # explicit exclusions, age/capacity constraints and hard budgets filter.
        if requested_terms and not direct and not related:
            score -= 22
        if not interest_ok and not negative_hit:
            score -= 14
        if not weather_ok:
            score -= 16
        if explicit_weather_preference and str(effective.weather or "").upper() == "RAIN":
            indoor_count = 0
            outdoor_count = 0
            for resource_row in item.resources:
                if resource_row.resource_type == "ROOM":
                    continue
                if resource_row.resource_type == "PARTNER_RESOURCE":
                    weather_resource = db.get(PartnerResource, resource_row.resource_id)
                    if weather_resource is not None:
                        if bool(weather_resource.indoor): indoor_count += 1
                        else: outdoor_count += 1
            outing_text = f"{item.product_name} {item.theme} " + " ".join(str(row.resource_name or "") for row in item.resources)
            outdoor_count += sum(1 for term in ("城市阳台", "湖滨步行", "西湖漫步", "沿江", "公园", "骑行", "登山") if term in outing_text)
            score += min(24, indoor_count * 12) - min(24, outdoor_count * 10)
        if target_areas:
            candidate_areas = product_area_tokens(db, item)
            shared = target_areas & candidate_areas
            if shared:
                score += min(14, 7 * len(shared))
        if related and not direct:
            score += 8
        candidate = (score, direct, item)
        scored.append(candidate)
        if not weather_ok:
            weather_relaxed.append(candidate)

    seed_text = f"{request.conversation_id}:{request.question}"
    suggestions_items, direct_count = choose_assistant_products(
        scored,
        current_id=product.id if product else None,
        seed_text=seed_text,
        limit=3,
        budget_target=effective.budget if budget_explicit else None,
    )
    weather_notice = False
    if requested_terms and not direct_count and weather_relaxed:
        relaxed_items, relaxed_direct_count = choose_assistant_products(
            weather_relaxed,
            current_id=product.id if product else None,
            seed_text=f"{seed_text}:weather",
            limit=3,
        )
        # This fallback is only for the unlikely case that all strict-ranked
        # options were removed upstream; weather itself is not a hard filter.
        seen = {item.id for item in suggestions_items}
        suggestions_items = [*suggestions_items, *[item for item in relaxed_items if item.id not in seen]][:3]
        direct_count = max(direct_count, relaxed_direct_count)
        weather_notice = bool(relaxed_items)
    if budget_explicit:
        # Stable sort keeps relevance order within each price group while putting
        # options at or below the visitor's target ahead of modest trade-offs.
        suggestions_items.sort(key=lambda item: item.suggested_price > effective.budget)
    selected_weather_mismatches = {
        item.id for _, _, item in weather_relaxed
    } & {item.id for item in suggestions_items}
    weather_notice = weather_notice or bool(selected_weather_mismatches)
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
    no_match_phrases = ("没有找到", "未找到", "暂无符合", "没有符合", "暂时没有匹配", "当前没有匹配")
    if suggestions_items and any(phrase in answer for phrase in no_match_phrases):
        party = (
            f"{effective.adult_count} 位成人、{effective.child_count} 位儿童"
            if effective.child_count
            else f"{effective.adult_count} 人同行"
        )
        first = suggestions_items[0]
        amount = Decimal(str(first.suggested_price))
        date_label = f"{first.target_date.month}月{first.target_date.day}日入住" if first.target_date else "可选日期见套餐卡片"
        budget_text = budget_label(conversation_text, effective.budget)
        price_tradeoff = ""
        if budget_explicit and amount > effective.budget and not budget_hard_limit:
            over = (amount - effective.budget).quantize(Decimal("0.01"))
            price_tradeoff = f"，比预算目标高 ¥{over}"
        answer = (
            f"按{party}和{budget_text}优先筛选，找到 {len(suggestions_items)} 个可选套餐。"
            f"首选「{first.product_name}」，{date_label}，¥{amount:.2f}/套，余 {first.sale_quantity} 套{price_tradeoff}。"
        )
    # 模型文字只能描述服务端通过硬条件筛选出的结果，不能将被筛掉的
    # 商品重新带回游客卡片；同名不同日期的产品也必须按 ID 分开保留。
    eligible_ids = {item.id for item in suggestions_items}
    eligible_names = {str(item.product_name) for item in suggestions_items if item.product_name}
    ineligible_names = {
        str(item.product_name)
        for item in visible_products
        if item.product_name and item.id not in eligible_ids and str(item.product_name) not in eligible_names and str(item.product_name) in answer
    }
    if ineligible_names:
        if requested_terms and direct_count:
            answer = f"按你提到的“{'、'.join(display_terms)}”，我筛出了 {direct_count} 个直接匹配且符合当前条件的在售方案。"
        elif requested_terms and suggestions:
            answer = f"目前没有完全匹配“{'、'.join(display_terms)}”的方案，下面列出符合当前条件的相近选择。"
        elif not suggestions:
            answer = "当前没有找到同时符合你已提供条件的在售方案。可以调整日期或偏好后再试。"
        else:
            answer = "我按你提供的条件筛选了以下在售方案。"
    if suggestions_items:
        suggestions = suggestions[:3]
    if suggestions_items and budget_explicit and (effective.target_crowd == "FAMILY" or effective.child_count > 0):
        first = suggestions_items[0]
        first_card = next((row for row in suggestions if int(row.get("id") or 0) == int(first.id)), {})
        amount = Decimal(str(first.suggested_price))
        party = (f"{effective.adult_count} 位成人、{effective.child_count} 位儿童" if effective.child_count else f"{effective.adult_count} 人同行")
        budget_text = budget_label(conversation_text, effective.budget)
        tradeoff = ""
        if amount > effective.budget and not budget_hard_limit:
            over = (amount - effective.budget).quantize(Decimal("0.01"))
            tradeoff = f"，比预算目标高 ¥{over}"
        date_label = f"{first.target_date.month}月{first.target_date.day}日" if first.target_date else "可选日期见套餐卡片"
        first_facts = safe_product_context(db, first)
        first_resources = first_card.get("resources") or []
        first_stay = first_card.get("stay") or {}
        included_labels: list[str] = []
        for resource in first_resources:
            resource_name = str(resource.get("resource_name") or "").strip()
            if not resource_name:
                continue
            quantity = max(1, int(resource.get("quantity_per_package") or 1))
            resource_type = str(resource.get("resource_type") or "")
            if resource_type == "ROOM":
                included_labels.append(f"{resource_name} × {quantity} 间 × {int(first_stay.get('nights') or 1)} 晚")
            elif resource_type == "PARTNER_RESOURCE":
                included_labels.append(f"{resource_name} × {quantity} 份")
            else:
                included_labels.append(resource_name)
        capacity = int(first_facts.get("room_max_guests") or 0)
        capacity_copy = f"房型最多入住 {capacity} 人" if capacity else ""
        inclusion_copy = "套餐安排包括" + "、".join(included_labels[:4]) if included_labels else "套餐内容见下方产品卡片"
        count_copy = f"；另有 {len(suggestions_items) - 1} 个可比较方案" if len(suggestions_items) > 1 else ""
        weather_copy = "户外环节与当前天气标签不完全匹配，建议优先选择卡片中适配天气的方案。" if first.id in selected_weather_mismatches else ""
        answer = (
            f"我按{party}、{budget_text}、房间可住人数和当前库存做了筛选；兴趣与天气用于排列顺序。当前有 {len(suggestions_items)} 个可售选择{count_copy}。"
            f"优先看「{first.product_name}」：{date_label}，¥{amount:.2f}/套，余 {int(first_card.get('sale_quantity') or 0)} 套{tradeoff}；{capacity_copy}。"
            f"{inclusion_copy}。{weather_copy}"
        )
    result_reasons: dict[str, str] = {}
    result_reason_tags: dict[str, list[str]] = {}
    result_reason_notes: dict[str, str] = {}
    assistant_candidate_ids = {str(item.id) for item in suggestions_items[:3]}
    current_resources = set()
    if product is not None:
        current_resources = {str(row.resource_name).strip() for row in product.resources
            if row.resource_type != "ROOM" and str(row.resource_name or "").strip()}
    for item in suggestions_items[:3]:
        key = str(item.id)
        facts = safe_product_context(db, item)
        amount = Decimal(str(item.suggested_price))
        searchable = recommendation_searchable_text(db, item).lower()
        experience_rows = [row for row in item.resources if row.resource_type in {"PARTNER_RESOURCE", "HOTEL_SERVICE"}]
        experiences = list(dict.fromkeys(str(row.resource_name).strip() for row in experience_rows if str(row.resource_name or "").strip()))
        details = visitor_payload(db, item)
        formal_rows = list(details.get("included_public_places") or [])
        formal_names = list(dict.fromkeys(str(row.get("resource_name") or row.get("title") or "").strip() for row in formal_rows if str(row.get("resource_name") or row.get("title") or "").strip()))
        included = list(dict.fromkeys([*experiences, *formal_names]))
        direct = [str(term).strip() for term in requested_terms if str(term).strip() and str(term).lower() in searchable]
        related = requested_categories & preference_categories(searchable)
        people = int(effective.adult_count or 0) + int(effective.child_count or 0)
        capacity = int(facts.get("room_max_guests") or 0)
        parts: list[str] = []
        tags: list[str] = []
        if people and capacity and people <= capacity:
            parts.append(f"房型最多入住{capacity}人，能容纳你们{people}位同行")
            tags.append(f"适合{people}人")
        elif item.target_crowd:
            crowd = {"FAMILY":"亲子家庭", "COUPLE":"情侣或双人", "FRIENDS":"朋友结伴", "SOLO":"独自出行", "ALL":"多人同行"}.get(str(item.target_crowd), "")
            if crowd:
                parts.append(f"产品定位更贴近{crowd}的游玩节奏")
                tags.append(crowd)
        if direct:
            matched = [name for name in included if any(term.lower() in name.lower() for term in direct)]
            focus = matched[:2] or direct[:2]
            parts.append("套餐实际包含" + "、".join(focus) + "，对应你提出的兴趣")
            tags.extend("含" + term[:6] for term in direct[:2])
        elif related:
            labels = [PREFERENCE_LABELS.get(value, value) for value in sorted(related)[:2]]
            if labels:
                parts.append("套餐中的" + "、".join(included[:2] or labels) + "与" + "、".join(labels) + "偏好相符")
                tags.extend(labels)
        elif included:
            parts.append("套餐核心内容是" + "、".join(included[:3]))
            tags.extend("含" + name[:6] for name in included[:2])
        if budget_explicit:
            if amount <= effective.budget:
                gap = (effective.budget - amount).quantize(Decimal("0.01"))
                parts.append(f"价格低于预算目标约¥{gap}，适合优先控制套餐开支")
                tags.append("预算内")
            else:
                over = (amount - effective.budget).quantize(Decimal("0.01"))
                benefit = "、".join(included[:2])
                parts.append(f"比预算目标高约¥{over}" + (f"，换来{benefit}等更完整的主题体验" if benefit else "，属于需要权衡的加价选择"))
                tags.append(f"高出预算¥{over:.0f}")
        if asks_for_alternatives and not explicitly_avoids_current_product and current_resources and experiences:
            retained = [name for name in experiences if name in current_resources]
            changed = [name for name in experiences if name not in current_resources]
            if changed and retained:
                parts.append(f"与当前套餐相比仍保留{retained[0]}，并把体验重点转向{changed[0]}")
            elif changed:
                parts.append(f"与当前套餐相比，主题改为{changed[0]}，适合想换一种玩法的人")
        reason_parts: list[str] = []
        note_parts: list[str] = []
        tags: list[str] = []
        child_count = int(effective.child_count or 0)
        adult_count = int(effective.adult_count or 0)
        if child_count:
            tags.append("一家三口同行" if adult_count == 2 and child_count == 1 else "亲子同行")
            family_ticket = next((
                row for row in item.resources
                if row.resource_type in {"PARTNER_RESOURCE", "HOTEL_SERVICE"}
                and any(word in str(row.resource_name or "") for word in ("乐园", "家庭日票"))
            ), None)
            if family_ticket and people:
                ticket_quantity = max(1, int(family_ticket.quantity_per_package or 1))
                if ticket_quantity >= people:
                    reason_parts.append(
                        f"「{family_ticket.resource_name}」按{ticket_quantity}份列入套餐，覆盖本次{people}人同行；住宿与亲子主活动可在同一方案里一起确认"
                    )
        elif people == 2:
            tags.append("双人同行")
        elif item.target_crowd:
            crowd = {"FAMILY":"亲子同行","COUPLE":"双人同行","FRIENDS":"朋友结伴","SOLO":"独自出行","ALL":"多人同行"}.get(str(item.target_crowd), "")
            if crowd:
                tags.append(crowd)

        detail_rows = details.get("resources") or []
        paid_rows = [row for row in detail_rows if row.get("resource_type") in {"PARTNER_RESOURCE", "HOTEL_SERVICE"}]
        paid_names = list(dict.fromkeys(str(row.get("resource_name") or "").strip() for row in paid_rows if row.get("resource_name")))
        included_names = list(dict.fromkeys([*paid_names, *formal_names[:2]]))
        if direct:
            matched = [name for name in included_names if any(term.lower() in name.lower() for term in direct)]
            focus = matched[:2] or direct[:2]
            reason_parts.append(f"你提到的「{'、'.join(direct[:2])}」在套餐里对应「{'、'.join(focus)}」，可以作为这趟出行的体验重点")
            tags.extend("含" + name[:6] for name in focus[:2])
        elif related:
            labels = [PREFERENCE_LABELS.get(value, value) for value in sorted(related)[:2]]
            if labels:
                reason_parts.append(f"这套的「{'、'.join(paid_names[:1] or formal_names[:1] or included_names[:1])}」和你偏好的「{'、'.join(labels)}」方向相符")
                tags.extend(labels)

        if paid_names:
            descriptions = [str(row.get("description") or "") for row in paid_rows]
            detail = next((text.split("。")[0].strip("；;，, ") for text in descriptions if len(text) > 14), "")
            if detail:
                reason_parts.append(f"核心体验「{paid_names[0]}」的具体玩法是{detail.rstrip('。')}")
            elif not direct and not related:
                reason_parts.append(f"它把「{paid_names[0]}」作为主要体验，适合希望行程里有明确参与内容的人")
            tags.append("含" + paid_names[0][:7])
        elif formal_names and not reason_parts:
            reason_parts.append(f"这套以「{'、'.join(formal_names[:2])}」作为正式行程主线，适合想围绕杭州城市漫游安排周末的人")

        family_focus = "、".join(included_names)
        if child_count and any(word in family_focus for word in ("乐园", "亲子", "家庭日票")):
            reason_parts.append("这让周末有一个明确的亲子主活动；和手作或城市漫步相比，更适合孩子本身就期待游乐园、家长希望少拼几项权益的家庭")
            note_parts.append("是否值得为乐园主题安排预算，主要看孩子是否喜欢这类游玩；出行前再按孩子年龄和身高核对园区项目要求。")
            tags.insert(0, "亲子主活动")
        elif child_count and any(word in family_focus for word in ("甜品", "烘焙", "手作", "陶艺")):
            reason_parts.append("它把全家共同动手体验作为周末重点，适合孩子喜欢制作、家长也想参与同一项活动的家庭；相比乐园型套餐，玩法更偏手作而不是游乐设施")
            note_parts.append("如果孩子最期待的是大型游乐项目，这套手作体验的方向会不同，优先选择更符合孩子兴趣的主题。")

        if asks_for_alternatives and not explicitly_avoids_current_product and current_resources and experiences:
            changed = [name for name in experiences if name not in current_resources]
            if changed:
                reason_parts.append(f"和当前套餐相比，玩法重点转为「{'、'.join(changed[:1])}」")

        if budget_explicit and effective.budget is not None:
            budget = Decimal(str(effective.budget))
            gap = budget - amount
            if gap < 0:
                over = int(abs(gap).quantize(Decimal("1")))
                value_item = paid_names[0] if paid_names else (formal_names[0] if formal_names else item.theme)
                reason_parts.append(f"多出的预算对应「{value_item}」这项实际体验，只有确实看重它时，上浮才有价值")
                note_parts.append(f"比约¥{budget:.0f}的目标高约¥{over}；若¥{budget:.0f}是硬上限，不建议优先选")
                tags.append("预算可上浮")
            else:
                tags.append("预算范围内")

        if explicit_weather_preference and str(effective.weather or "").upper() == "RAIN":
            indoor, outdoor = [], []
            for row in item.resources:
                if row.resource_type == "PARTNER_RESOURCE":
                    source = db.get(PartnerResource, row.resource_id)
                    if source:
                        (indoor if source.indoor else outdoor).append(str(row.resource_name or "体验"))
            outdoor.extend(name for name in formal_names if any(word in name for word in ("步行街", "城市阳台", "西湖")))
            if indoor and outdoor:
                note_parts.append(f"室内的「{indoor[0]}」可保留；「{outdoor[0]}」偏户外，雨势大时建议缩短停留")
            elif outdoor:
                note_parts.append(f"「{outdoor[0]}」偏户外，雨势大时需要调整游玩时长")
            elif indoor:
                note_parts.append(f"主要体验「{indoor[0]}」在室内，雨天影响较小")

        if not reason_parts:
            reason_parts.append(f"这套围绕「{'、'.join(included_names[:2]) or item.theme or '杭州周末体验'}」安排，适合希望把住宿和主要活动一次规划的人")
        reason_text = "。".join(part.strip().rstrip("。；;，,") for part in reason_parts if part.strip())
        result_reasons[key] = reason_text.rstrip("。；; ") + "。"
        note_text = "。".join(part.strip().rstrip("。；;，,") for part in note_parts if part.strip())
        result_reason_notes[key] = note_text.rstrip("。；; ") + ("。" if note_text else "")
        result_reason_tags[key] = list(dict.fromkeys(tags))[:3]

    # Replace generic model prose with a short comparison grounded in the
    # exact products already filtered above. This keeps the narrative and the
    # visible product cards consistent on price, date, capacity and inventory.
    criteria: list[str] = []
    if effective.child_count:
        criteria.append(f"{effective.adult_count} 位成人和 {effective.child_count} 位儿童")
    elif effective.adult_count:
        criteria.append(f"{effective.adult_count} 人同行")
    if effective.target_crowd not in {"", "ALL"} and not (effective.adult_count or effective.child_count):
        crowd_text = {"FAMILY": "亲子出行", "COUPLE": "双人同行", "FRIENDS": "朋友同行", "SOLO": "独自出行"}.get(str(effective.target_crowd), "")
        if crowd_text and crowd_text not in "、".join(criteria):
            criteria.append(crowd_text)
    if budget_explicit:
        criteria.append(f"预算目标约 ¥{effective.budget:.0f}")
    if effective.target_date:
        criteria.append(f"{effective.target_date.month}月{effective.target_date.day}日出行")
    if display_terms:
        criteria.append("偏好" + "、".join(display_terms[:3]))

    if suggestions_items:
        filter_copy = "、".join(criteria) if criteria else "你刚刚提到的出行条件"
        first = suggestions_items[0]
        first_card = next((row for row in suggestions if int(row.get("id") or 0) == int(first.id)), {})
        first_payload = visitor_payload(db, first)
        first_stay = first_payload.get("stay") or {}
        first_resource_rows = first_payload.get("resources") or []
        first_paid = [str(row.get("resource_name") or "") for row in first_resource_rows
                      if row.get("resource_type") in {"PARTNER_RESOURCE", "HOTEL_SERVICE"} and row.get("resource_name")]
        first_room = str(first_stay.get("room_name") or "住宿")
        first_places = list(dict.fromkeys(str(row.get("resource_name") or row.get("title") or "")
                         for row in (first_payload.get("included_public_places") or [])
                         if row.get("resource_name") or row.get("title")))
        context_bits: list[str] = []
        if effective.child_count:
            context_bits.append(f"{effective.adult_count}位成人带{effective.child_count}位儿童")
        elif effective.adult_count:
            context_bits.append(f"{effective.adult_count}人同行")
        if budget_explicit and effective.budget is not None:
            context_bits.append(f"预算约¥{effective.budget:.0f}")
        if effective.target_date:
            context_bits.append(f"{effective.target_date.month}月{effective.target_date.day}日出行")
        if display_terms:
            context_bits.append("偏好" + "、".join(display_terms[:2]))
        context_copy = "、".join(context_bits)
        feature_names = list(dict.fromkeys([*first_paid[:2], *first_places[:2]]))
        feature_copy = "、".join(feature_names) or str(first.theme or "杭州周末体验")
        first_amount = Decimal(str(first.suggested_price))
        lead_prefix = f"{context_copy}，" if context_copy else ""
        lead = f"{lead_prefix}我更推荐「{first.product_name}」：这套以{feature_copy}为主线，住宿和主要体验已经组合好，适合想把周末安排得省心一些的人。"
        if budget_explicit and effective.budget is not None:
            budget_delta = (Decimal(str(effective.budget)) - first_amount).quantize(Decimal("1"))
            if budget_delta >= 0:
                if budget_delta == 0:
                    lead += f"价格正好落在¥{effective.budget:.0f}预算内。"
                else:
                    lead += f"价格在预算范围内，适合把预算留给餐饮或交通。"
            else:
                over = int(abs(budget_delta))
                added_value = "、".join(first_paid[:2] or first_places[:2]) or str(first.theme or "主要体验")
                lead += f"它会比预算目标高约¥{over}；这笔上浮是否值得，取决于你们是否会实际体验套餐里的{added_value}。如果预算能放宽且孩子喜欢这个主题，它更省去分别拼订住宿和主活动的步骤；若¥{effective.budget:.0f}是硬上限，就不建议勉强选择。"
        paragraphs = [lead]
        if product is not None and not explicitly_avoids_current_product:
            current_names = list(dict.fromkeys(
                str(row.resource_name).strip()
                for row in product.resources
                if row.resource_type != "ROOM" and str(row.resource_name or "").strip()
            ))
            retained = [name for name in feature_names if name in current_names]
            changed = [name for name in feature_names if name not in current_names]
            removed = [name for name in current_names if name not in feature_names]
            comparison = []
            if retained:
                comparison.append(f"仍保留{'、'.join(retained[:2])}")
            if removed and changed:
                comparison.append(f"把{'、'.join(removed[:1])}换成{'、'.join(changed[:1])}")
            elif changed:
                comparison.append(f"主体验转为{'、'.join(changed[:2])}")
            current_amount = Decimal(str(product.suggested_price or 0))
            price_change = (current_amount - first_amount).quantize(Decimal("1"))
            if price_change > 0:
                comparison.append(f"比当前套餐少约¥{int(price_change)}")
            elif price_change < 0:
                comparison.append(f"比当前套餐高约¥{int(abs(price_change))}")
            if comparison:
                paragraphs.append(
                    f"和你正在看的「{product.product_name}」相比，这款{'；'.join(comparison)}。"
                    f"如果更想保留{'、'.join(removed[:1]) or '原来的主体验'}，当前套餐更合适；"
                    f"如果更看重{'、'.join(changed[:1]) or feature_copy}，这款更值得优先比较。"
                )
        elif product is not None and explicitly_avoids_current_product:
            paragraphs.append("你已经说明不考虑正在看的产品，这次候选都来自其他在售套餐；下方会直接按亲子主题、预算取舍和实际套餐权益说明各自适合的情况。")
        elif len(suggestions_items) == 1:
            day_count = len(first_payload.get("day_plan") or []) or int(first_stay.get("nights") or 1) + 1
            paragraphs.append(f"这趟约{day_count}天，重点是{feature_copy}；如果这正是你想安排的主题，这款值得优先看。")

        if len(suggestions_items) > 1:
            second = suggestions_items[1]
            second_payload = visitor_payload(db, second)
            second_resources = second_payload.get("resources") or []
            second_paid = list(dict.fromkeys(
                str(row.get("resource_name") or "").strip()
                for row in second_resources
                if row.get("resource_type") in {"PARTNER_RESOURCE", "HOTEL_SERVICE"} and row.get("resource_name")
            ))
            second_places = list(dict.fromkeys(
                str(row.get("resource_name") or row.get("title") or "").strip()
                for row in (second_payload.get("included_public_places") or [])
                if row.get("resource_name") or row.get("title")
            ))
            second_focus = "、".join(second_paid[:1] or second_places[:1]) or str(second.theme or "另一种主题")
            first_focus = "、".join(first_paid[:1] or first_places[:1]) or str(first.theme or "当前首选")
            if effective.child_count:
                conclusion = (
                    f"综合建议：孩子更期待「{first_focus}」且预算能上浮时，首选「{first.product_name}」；"
                    f"如果全家更偏好「{second_focus}」，第二款的玩法更合适。"
                )
            else:
                conclusion = (
                    f"综合建议：更看重「{first_focus}」就优先选「{first.product_name}」；"
                    f"如果更想体验「{second_focus}」，再选「{second.product_name}」，两款的核心玩法不同。"
                )
            if budget_explicit and effective.budget is not None:
                budget = Decimal(str(effective.budget))
                within_budget = [candidate for candidate in suggestions_items[:3]
                                 if Decimal(str(candidate.suggested_price)) <= budget]
                if within_budget:
                    budget_pick = min(within_budget, key=lambda candidate: Decimal(str(candidate.suggested_price)))
                    conclusion += f"若预算必须控制在¥{budget:.0f}以内，优先看「{budget_pick.product_name}」。"
                else:
                    conclusion += f"这次列出的方案都高于¥{budget:.0f}；若这是硬上限，不建议勉强接受超预算方案。"
            paragraphs.append(conclusion)

        answer = "\n\n".join(paragraphs)

    else:
        constraint_copy = "、".join(criteria) or "当前可选的出行条件"
        answer = f"按{constraint_copy}查找后，当前在售库存里没有同时符合的方案。主要限制是已给出的日期、人数或排除条件；如果你调整其中一项，我会保留其他条件重新查找。"

    safety_text = visitor_answer_copy(getattr(result.value, "safety_notes", ""))
    if not any(term in conversation_text for term in ("过敏", "忌口", "年龄", "适龄", "安全", "无障碍", "儿童限制")):
        # Cross-product notes from the language model are too easy to mistake
        # for conditions on the recommended package. General recommendations
        # use per-product reasons and follow-up questions instead.
        safety_text = ""
    return {
        "mode": "discovery",
        "trace_id": result.trace_id,
        # 面向游客的正文一律经过中文枚举转换：模型偶尔会复述 FAMILY / RAIN 这类内部字段。
        "answer": localize_internal_labels(answer),
        "safety_notes": localize_internal_labels(safety_text),
        # 结构化推荐依据：让助手回答不止一段话，而是「为什么推荐 / 时间怎么排 / 哪些改不了」。
        "reasons": {
            str(key): localize_internal_labels(text)
            for key, text in result_reasons.items()
        },
        "reason_tags": {
            str(key): [localize_internal_labels(tag) for tag in tags]
            for key, tags in result_reason_tags.items()
        },
        "reason_notes": {
            str(key): localize_internal_labels(note)
            for key, note in result_reason_notes.items()
            if note
        },
        "schedule_notes": {
            str(key): [
                {**item, "content": localize_internal_labels(item.get("content", ""))}
                if isinstance(item, dict)
                else localize_internal_labels(item)
                for item in (items or [])
            ]
            for key, items in (getattr(result.value, "schedule_notes", None) or {}).items()
            if str(key) in assistant_candidate_ids
        },
        "limited_adjustments": {
            str(key): [localize_internal_labels(text) for text in items]
            if isinstance(items, list)
            else [localize_internal_labels(items)]
            for key, items in (getattr(result.value, "limited_adjustments", None) or {}).items()
            if str(key) in assistant_candidate_ids
        },
        "product": visitor_payload(db, product) if product and not asks_for_alternatives else None,
        "suggestions": suggestions,
        # 换房型问题直接给出可点链接所需的数据（当前套餐 + 各房型 id/价格/余量）。
        "product_id": None if asks_for_alternatives else product.id if product else None,
        "room_options": payload.get("room_options") or [],
        "follow_up_questions": follow_up_questions(
            effective.model_copy(update={
                "budget": effective.budget if budget_explicit else None,
                "target_date": effective.target_date if re.search(r"(?:\d{1,2}[月/.-]\d{1,2}|今天|明天|后天|周末|本周|下周|周[一二三四五六日天])", conversation_text) else None,
            }),
            interpreted_needs(effective, conversation_text),
        )[:2],
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
    db.commit()
    output = agent_result.value
    output_ids = set(output.selected_product_ids)
    ranked_candidates = sorted(valid_candidates, key=lambda product: match_meta[product.id][3], reverse=True)
    model_selected = [item for item in ranked_candidates if item.id in output_ids]
    selected_ids = {item.id for item in model_selected}
    result_candidates = [*model_selected, *[item for item in ranked_candidates if item.id not in selected_ids]][:3]
    results = []
    for item in result_candidates:
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


def _intent_submission_view(intent: VisitorIntent, product: TravelProduct | None, *, replayed: bool = False) -> dict[str, Any]:
    """One response shape for both a fresh submission and an idempotent replay."""

    snapshot = intent.recommendation_result if isinstance(intent.recommendation_result, dict) else {}
    phone = intent.contact_phone or ""
    masked = phone[:3] + "****" + phone[-4:] if len(phone) >= 7 else "***"
    remaining = snapshot.get("remaining_quantity")
    if remaining is None:
        remaining = int(product.sale_quantity) if product is not None else 0
    return {
        "id": intent.id,
        "product_id": intent.product_id,
        "product_name": snapshot.get("product_name") or (product.product_name if product is not None else ""),
        "intent_status": intent.intent_status,
        "reservation_status": intent.reservation_status,
        "reserved_until": intent.reserved_until,
        "submitted_quantity": snapshot.get("submitted_quantity", 0),
        "remaining_quantity": remaining,
        "product_status": snapshot.get("status_after_submission") or (product.status if product is not None else ""),
        "contact_phone_masked": masked,
        "message": (
            "这条购买请求已经受理过，返回的是同一次提交的结果，没有重复占用库存。"
            if replayed
            else "购买信息已提交，已暂占用房量、酒店服务和合作体验名额；酒店会在保留时间内联系确认。"
        ),
    }


@router.post("/intents")
async def create_intent(request: VisitorIntentCreate, db: Session = Depends(get_db)):
    if sweep_expired_intents(db):
        db.commit()
    request_key = (request.client_request_id or "").strip()
    if request_key:
        # A retried submission must return the first result instead of
        # reserving a second room and a second experience slot.
        existing = db.scalar(
            select(VisitorIntent).where(
                VisitorIntent.product_id == request.product_id,
                VisitorIntent.client_request_id == request_key,
            )
        )
        if existing is not None:
            return _intent_submission_view(existing, db.get(TravelProduct, existing.product_id), replayed=True)
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
        "client_request_id": request_key,
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
    try:
        db.flush()
    except IntegrityError:
        # Two concurrent retries raced past the lookup above; the unique index
        # rejected the loser, so roll back its reservation and replay the win.
        db.rollback()
        existing = db.scalar(
            select(VisitorIntent).where(
                VisitorIntent.product_id == request.product_id,
                VisitorIntent.client_request_id == request_key,
            )
        )
        if existing is None:
            raise
        return _intent_submission_view(existing, db.get(TravelProduct, existing.product_id), replayed=True)
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
    return _intent_submission_view(intent, product)


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
