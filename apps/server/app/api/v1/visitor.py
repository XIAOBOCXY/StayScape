import re
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
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
from ...services.serializers import product_to_dict
from ...rules.availability_rule import tokens
from ...rules.crowd_rule import crowd_supported
from ...rules.time_rule import intervals_overlap
from ...rules.weather_rule import is_weather_supported
from ..websocket_manager import manager

router = APIRouter(prefix="/visitor", tags=["visitor"])


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
    "SLOW": ("慢游", "休息", "安静", "放松", "slow"),
}
NEGATIVE_MARKERS = ("不想", "不要", "不喜欢", "不爱", "避开", "别安排", "不考虑")


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
    if family_match and "adult_count" not in updates and ages:
        updates["adult_count"] = max(number_value(family_match.group(1), request.adult_count) - len(ages), 1)
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
    arrival_match = re.search(r"(?:下午|晚上|早上|上午)?\s*([一二两三四五六七八九十\d]{1,2})\s*点", text)
    if arrival_match and request.arrival_time is None:
        hour = number_value(arrival_match.group(1), 15)
        if "下午" in text or "晚上" in text:
            hour = hour + 12 if hour < 12 else hour
        updates["arrival_time"] = time(min(hour, 23), 0)
    effective = request.model_copy(update=updates)
    interpreted = {
        "natural_language": text,
        "weather": effective.weather,
        "target_crowd": effective.target_crowd,
        "budget": str(effective.budget),
        "adult_count": effective.adult_count,
        "child_count": effective.child_count,
        "child_ages": effective.child_ages,
        "interests": effective.interests,
        "negative_interests": effective.negative_interests,
        "activity_level": effective.activity_level,
        "requested_places": effective.requested_places,
        "dietary_restrictions": effective.dietary_restrictions,
        "allergy_information": effective.allergy_information,
        "other_requirements": effective.other_requirements or text,
    }
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


def public_items(db: Session, query: VisitorProductQuery | None = None) -> list[TravelProduct]:
    products = list_products(db, public_only=True)
    if query and query.target_date:
        products = [item for item in products if item.target_date == query.target_date]
    if query and query.budget:
        products = [item for item in products if item.suggested_price <= query.budget]
    if query and query.target_crowd:
        products = [item for item in products if item.target_crowd == query.target_crowd or item.target_crowd == "ALL"]
    if query and query.interest:
        needle = query.interest.lower()
        products = [item for item in products if needle in f"{item.product_name} {item.theme} {item.marketing_content}".lower() or not needle]
    return products


def product_partner_rows(db: Session, product: TravelProduct) -> list[tuple[ProductResource, PartnerResource]]:
    result = []
    for row in product.resources:
        if row.resource_type == "PARTNER_RESOURCE":
            resource = db.get(PartnerResource, row.resource_id)
            if resource:
                result.append((row, resource))
    return result


def matches_conditions(db: Session, product: TravelProduct, request: VisitorRecommendRequest) -> tuple[bool, bool, bool, int]:
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
    interest_match = persona_match and activity_match and not negative_hit and positive_match
    budget_match = product.suggested_price <= request.budget
    score = (35 if budget_match else 0) + (25 if children_match else 0) + (20 if weather_match else 0) + (20 if interest_match else 0)
    return children_match, weather_match, interest_match, score


def build_schedule(db: Session, product: TravelProduct, arrival: time | None = None, preferred: time | None = None) -> list[dict[str, str]]:
    check_in = max(time(15, 0), arrival or time(15, 0))
    schedule = [{"time": check_in.strftime("%H:%M"), "title": "办理入住", "description": "酒店前台办理入住，领取套餐时间卡"}]
    for row in product.resources:
        if row.resource_type == "HOTEL_SERVICE":
            service = db.get(HotelService, row.resource_id)
            if service and service.start_time and (not arrival or service.start_time >= arrival):
                schedule.append({"time": service.start_time.strftime("%H:%M"), "title": service.service_name, "description": f"每套使用{row.quantity_per_package}份"})
        elif row.resource_type == "PARTNER_RESOURCE":
            resource = db.get(PartnerResource, row.resource_id)
            if resource and resource.start_time and (not arrival or resource.start_time >= arrival):
                schedule.append({"time": resource.start_time.strftime("%H:%M"), "title": resource.resource_name, "description": f"地址：{resource.address}"})
    schedule.sort(key=lambda item: item["time"])
    if preferred:
        schedule.append({"time": preferred.strftime("%H:%M"), "title": "游客偏好时段", "description": "最终场次以商户实时确认结果为准"})
    return schedule


@router.get("/products", response_model=list[ProductRead])
def products(query: VisitorProductQuery = Depends(), db: Session = Depends(get_db)):
    if sweep_expired_intents(db):
        db.commit()
    return [product_to_dict(item) for item in public_items(db, query)]


@router.get("/products/{product_id}", response_model=ProductRead)
def product_detail(product_id: int, db: Session = Depends(get_db)):
    if sweep_expired_intents(db):
        db.commit()
    product = get_product(db, product_id)
    if not product or product.status not in {"ON_SALE", "LOW_STOCK"} or product.sale_quantity <= 0:
        raise AppError("NOT_FOUND", "当前套餐不存在或已下架", status_code=404)
    return product_to_dict(product)


@router.post("/consult")
def consult(request: VisitorQuestion, db: Session = Depends(get_db)):
    product = get_product(db, request.product_id) if request.product_id else None
    if product and (product.status not in {"ON_SALE", "LOW_STOCK"} or product.sale_quantity <= 0):
        product = None
    interpreted_request, _ = enrich_recommend_request(VisitorRecommendRequest(natural_language=request.natural_language or request.question, weather=request.weather, target_crowd=product.target_crowd if product else "FAMILY"))
    payload = {
        "question": request.question,
        "natural_language": request.natural_language or request.question,
        "weather": request.weather,
        "target_crowd": interpreted_request.target_crowd,
        "negative_interests": interpreted_request.negative_interests,
        "activity_level": interpreted_request.activity_level,
        "products": [{"id": product.id, "product_name": product.product_name, "sale_quantity": product.sale_quantity}] if product else [],
        "allergy_information": "",
    }
    result = AgentOrchestrator(db, hotel_id=product.hotel_id if product else None).match_visitor(payload)
    answer = getattr(result.value, "answer", "") or "我会结合当前可售库存、预算、客群、天气和体验时间给出推荐；最终库存与价格以系统实时计算为准。"
    suggestions = []
    if any(word in question for word in ("还有", "其他", "推荐", "别的")):
        effective = VisitorRecommendRequest(natural_language=request.question, weather=request.weather, budget=product.visitor_budget_limit if product else Decimal("700"), target_date=product.target_date if product else None, target_crowd=product.target_crowd if product else "FAMILY")
        effective, _ = enrich_recommend_request(effective)
        candidates = []
        for item in list_products(db, public_only=True):
            if product and item.id == product.id:
                continue
            if effective.target_date and item.target_date != effective.target_date:
                continue
            if item.suggested_price > effective.budget:
                continue
            child_ok, weather_ok, interest_ok, _ = matches_conditions(db, item, effective)
            if child_ok and weather_ok and interest_ok and not effective.negative_interests:
                candidates.append(item)
        suggestions = [product_to_dict(item) for item in candidates[:3]]
    return {"trace_id": result.trace_id, "answer": answer, "safety_notes": getattr(result.value, "safety_notes", "") or "AI建议不替代商户对过敏、儿童安全和场次的最终确认。", "product": product_to_dict(product) if product else None, "suggestions": suggestions, "follow_up_questions": ["同行人数和儿童年龄是多少？", "更想去西湖、运河还是室内文化体验？", "预算上限和可接受场次是什么？"], "fallback_used": result.fallback_used}


@router.post("/interpret", response_model=VisitorInterpretResponse)
def interpret(request: VisitorInterpretRequest):
    effective, interpreted = enrich_recommend_request(VisitorRecommendRequest(natural_language=request.natural_language))
    return {"interpreted_needs": interpreted, "follow_up_questions": follow_up_questions(effective, interpreted)}


@router.post("/recommend")
def recommend(request: VisitorRecommendRequest, db: Session = Depends(get_db)):
    request, interpreted_needs = enrich_recommend_request(request)
    candidates = list_products(db, public_only=True)
    if request.target_date:
        candidates = [item for item in candidates if item.target_date == request.target_date]
    valid_candidates = []
    match_meta: dict[int, tuple[bool, bool, bool, int]] = {}
    for item in candidates:
        if item.sale_quantity <= 0 or item.suggested_price > request.budget:
            continue
        children_match, weather_match, interest_match, score = matches_conditions(db, item, request)
        if not children_match or not weather_match:
            continue
        if request.target_crowd and item.target_crowd not in {request.target_crowd, "ALL"}:
            continue
        if (request.negative_interests or request.activity_level != "MEDIUM") and not interest_match:
            continue
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
        "products": [{"id": item.id, "product_name": item.product_name, "sale_quantity": item.sale_quantity} for item in valid_candidates],
    }
    hotel_ids = {item.hotel_id for item in valid_candidates}
    agent_result = AgentOrchestrator(db, hotel_id=next(iter(hotel_ids)) if len(hotel_ids) == 1 else None).match_visitor(payload)
    output = agent_result.value
    output_ids = set(output.selected_product_ids)
    results = []
    for item in sorted(valid_candidates, key=lambda product: match_meta[product.id][3], reverse=True):
        children_match, weather_match, interest_match, score = match_meta[item.id]
        reason = output.reasons.get(str(item.id), item.recommendation_reason)
        results.append({
            "product": product_to_dict(item),
            "score": min(100, score + (3 if item.id in output_ids else 0)),
            "recommendation_reason": reason,
            "budget_match": item.suggested_price <= request.budget,
            "children_match": children_match,
            "weather_match": weather_match,
            "interest_match": interest_match,
            "schedule": build_schedule(db, item, request.arrival_time, request.preferred_experience_time),
            "limited_adjustments": output.limited_adjustments.get(str(item.id)) or ["预约意向中可备注希望的体验场次", "实时名额变化后以酒店与商户确认结果为准"],
            "allergy_warning": output.allergy_warning or None,
        })
    return {"results": results, "trace_id": agent_result.trace_id, "fallback_used": agent_result.fallback_used, "interpreted_needs": interpreted_needs}


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
        raise AppError("PRODUCT_UNAVAILABLE", "当前套餐已无法提交预约意向", retryable=True)
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
    if request.natural_language.strip():
        effective, _ = enrich_recommend_request(effective)
    if effective.child_count and len(effective.child_ages) != effective.child_count:
        raise AppError("VALIDATION_ERROR", "儿童人数与儿童年龄数量不一致", field="child_ages")
    children_match, weather_match, _, _ = matches_conditions(db, product, effective)
    if not children_match:
        raise AppError("VISITOR_CONSTRAINT_NOT_MET", "同行人数、儿童年龄或到店时间不符合该套餐约束", field="adult_count", retryable=True)
    if not weather_match:
        raise AppError("WEATHER_NOT_SUPPORTED", "该套餐内体验不支持游客填写的天气场景", field="weather", retryable=True)
    if product.suggested_price > effective.budget:
        raise AppError("BUDGET_EXCEEDED", "套餐价格超过游客预算上限", field="budget", retryable=True)

    previous_quantity = product.sale_quantity
    previous_status = product.status
    allocation_snapshot = reserve_product_inventory(db, product)
    allocation_snapshot.update({"product_quantity_before": previous_quantity, "product_status_before": previous_status})
    product.sale_quantity -= 1
    product.status = "SOLD_OUT" if product.sale_quantity <= 0 else ("LOW_STOCK" if product.sale_quantity <= 2 else product.status)
    result = {
        "product_id": product.id,
        "product_name": product.product_name,
        "submitted_price": str(product.suggested_price),
        "submitted_quantity": previous_quantity,
        "remaining_quantity": product.sale_quantity,
        "status_after_submission": product.status,
        "allergy_information": effective.allergy_information,
    }
    intent_data = request.model_dump(exclude={"natural_language", "negative_interests", "activity_level"})
    intent_data.update({
        "adult_count": effective.adult_count,
        "child_count": effective.child_count,
        "child_ages": effective.child_ages,
        "budget": effective.budget,
        "interests": effective.interests,
        "dietary_restrictions": effective.dietary_restrictions,
        "allergy_information": effective.allergy_information,
        "other_requirements": effective.other_requirements or request.natural_language,
    })
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
            reason="游客提交预约意向，事务性占用客房、酒店服务和合作体验名额",
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
                reason="游客预约意向暂占用套餐底层库存",
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
            "title": "收到新的游客预约意向",
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
        "message": "预约意向已提交，已暂占用房量、酒店服务和合作体验名额；酒店会在保留时间内联系确认。",
    }


@router.post("/intents/{intent_id}/cancel")
def cancel_intent(intent_id: int, request: VisitorIntentCancelRequest, db: Session = Depends(get_db)):
    if sweep_expired_intents(db):
        db.commit()
    intent = db.scalar(select(VisitorIntent).where(VisitorIntent.id == intent_id).with_for_update())
    if not intent or intent.contact_phone != request.contact_phone:
        raise AppError("NOT_FOUND", "预约意向不存在或联系方式不匹配", status_code=404)
    if intent.reservation_status not in {"HELD", "CONFIRMED"}:
        return {"id": intent.id, "reservation_status": intent.reservation_status, "message": "该预约意向已经结束，无需重复释放"}
    result = release_intent_inventory(db, intent)
    reconcile_published_capacity(db, intent.product.hotel_id if intent.product else 0)
    db.commit()
    return {"id": intent.id, "reservation_status": intent.reservation_status, "intent_status": intent.intent_status, "message": "预约意向已取消，库存已释放", "inventory": result}


@router.get("/public-resources")
def public_resources(db: Session = Depends(get_db), weather: str = "RAIN"):
    items = list(db.scalars(select(PublicResource).where(PublicResource.status == "ACTIVE").order_by(PublicResource.id)).all())
    return [{"id": item.id, "resource_name": item.resource_name, "category": item.category, "description": item.description, "address": item.address, "opening_hours": item.opening_hours, "weather_supported": is_weather_supported(item.weather_tags, weather), "source": item.source} for item in items]
