import re
from datetime import date, time, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...agent import AgentOrchestrator
from ...core.exceptions import AppError
from ...db import get_db
from ...models import HotelService, PartnerResource, ProductResource, PublicResource, TravelProduct, VisitorIntent
from ...repositories.product_repository import get_product, list_products
from ...schemas.products import ProductRead
from ...schemas.visitor import VisitorIntentCreate, VisitorProductQuery, VisitorQuestion, VisitorRecommendRequest
from ...services.serializers import product_to_dict
from ...rules.availability_rule import tokens
from ...rules.crowd_rule import crowd_supported
from ...rules.time_rule import intervals_overlap
from ...rules.weather_rule import is_weather_supported

router = APIRouter(prefix="/visitor", tags=["visitor"])


CN_NUMBERS = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


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
    if "明天" in text:
        updates["target_date"] = date.today() + timedelta(days=1)
    elif "今天" in text:
        updates["target_date"] = date.today()
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
    adult_match = re.search(r"(\d+|[一二两三四五六七八九十])\s*(?:位)?大人", text)
    if adult_match:
        value = adult_match.group(1)
        updates["adult_count"] = int(value) if value.isdigit() else CN_NUMBERS.get(value, request.adult_count)
    child_count_match = re.search(r"(\d+|[一二两三四五六七八九十])\s*(?:位)?(?:个)?(?:小孩|儿童|孩子|小朋友)", text)
    if child_count_match and "child_count" not in updates:
        value = child_count_match.group(1)
        updates["child_count"] = int(value) if value.isdigit() else CN_NUMBERS.get(value, request.child_count)
    if any(word in text for word in ("情侣", "夫妻", "两个人", "两人")) and not any(word in text for word in ("孩子", "儿童", "小孩", "小朋友", "岁")):
        updates["child_count"] = 0
        updates["child_ages"] = []
    interests = [word for word in ("亲子", "手工", "非遗", "茶", "点茶", "博物馆", "摄影", "旅拍", "美食", "慢游") if word in text]
    if interests:
        updates["interests"] = list(dict.fromkeys([*request.interests, *interests]))
    allergy_terms = [word for word in ("花生", "坚果", "牛奶", "乳制品", "海鲜", "鸡蛋", "不吃辣", "素食") if word in text]
    if allergy_terms:
        updates["dietary_restrictions"] = list(dict.fromkeys([*request.dietary_restrictions, *allergy_terms]))
        updates["allergy_information"] = request.allergy_information or "、".join(allergy_terms)
    effective = request.model_copy(update=updates)
    interpreted = {
        "natural_language": text,
        "weather": effective.weather,
        "budget": str(effective.budget),
        "adult_count": effective.adult_count,
        "child_count": effective.child_count,
        "child_ages": effective.child_ages,
        "interests": effective.interests,
        "dietary_restrictions": effective.dietary_restrictions,
        "allergy_information": effective.allergy_information,
    }
    return effective, interpreted


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
    for row, resource in product_partner_rows(db, product):
        if not is_weather_supported(resource.weather_tags, request.weather):
            weather_match = False
        if not crowd_supported(resource.suitable_crowds, product.target_crowd, request.child_ages, resource.minimum_age, resource.maximum_age):
            children_match = False
    if request.child_count and len(request.child_ages) != request.child_count:
        children_match = False
    interest_match = not request.interests or any(item.lower() in f"{product.product_name} {product.theme} {product.marketing_content}".lower() for item in request.interests)
    budget_match = product.suggested_price <= request.budget
    score = (35 if budget_match else 0) + (25 if children_match else 0) + (20 if weather_match else 0) + (20 if interest_match else 0)
    return children_match, weather_match, interest_match, score


def build_schedule(db: Session, product: TravelProduct, arrival: time | None = None, preferred: time | None = None) -> list[dict[str, str]]:
    schedule = [{"time": "15:00", "title": "办理入住", "description": "酒店前台办理入住，领取套餐时间卡"}]
    for row in product.resources:
        if row.resource_type == "HOTEL_SERVICE":
            service = db.get(HotelService, row.resource_id)
            if service and service.start_time:
                schedule.append({"time": service.start_time.strftime("%H:%M"), "title": service.service_name, "description": f"每套使用{row.quantity_per_package}份"})
        elif row.resource_type == "PARTNER_RESOURCE":
            resource = db.get(PartnerResource, row.resource_id)
            if resource and resource.start_time:
                schedule.append({"time": resource.start_time.strftime("%H:%M"), "title": resource.resource_name, "description": f"地址：{resource.address}"})
    schedule.sort(key=lambda item: item["time"])
    if preferred:
        schedule.append({"time": preferred.strftime("%H:%M"), "title": "游客偏好时段", "description": "最终场次以商户实时确认结果为准"})
    return schedule


@router.get("/products", response_model=list[ProductRead])
def products(query: VisitorProductQuery = Depends(), db: Session = Depends(get_db)):
    return [product_to_dict(item) for item in public_items(db, query)]


@router.get("/products/{product_id}", response_model=ProductRead)
def product_detail(product_id: int, db: Session = Depends(get_db)):
    product = get_product(db, product_id)
    if not product or product.status not in {"ON_SALE", "LOW_STOCK"} or product.sale_quantity <= 0:
        raise AppError("NOT_FOUND", "当前套餐不存在或已下架", status_code=404)
    return product_to_dict(product)


@router.post("/consult")
def consult(request: VisitorQuestion, db: Session = Depends(get_db)):
    product = get_product(db, request.product_id) if request.product_id else None
    if product and (product.status not in {"ON_SALE", "LOW_STOCK"} or product.sale_quantity <= 0):
        product = None
    payload = {
        "question": request.question,
        "weather": request.weather,
        "products": [{"id": product.id, "product_name": product.product_name, "sale_quantity": product.sale_quantity}] if product else [],
        "allergy_information": "",
    }
    result = AgentOrchestrator(db).match_visitor(payload)
    question = request.question
    if "雨" in question or "天气" in question:
        answer = "可以优先选择支持当前天气的室内体验；具体场次以商户实时名额和天气标签为准。"
    elif "儿童" in question or "岁" in question:
        answer = "系统会校验儿童年龄与体验的最低、最高年龄。若年龄不匹配，不会把该体验作为正式推荐。"
    elif "早餐" in question:
        answer = "套餐中的酒店服务会显示每套消耗量和时间，家庭早餐示例为每套3份。"
    elif "过敏" in question or "花生" in question:
        answer = "过敏信息只作为风险提示，请在预约意向中填写，并由酒店与商户在确认前再次人工核对。"
    else:
        answer = "我会结合当前可售库存、预算、客群、天气和体验时间给出推荐；最终库存与价格以系统实时计算为准。"
    return {"trace_id": result.trace_id, "answer": answer, "safety_notes": "AI建议不替代商户对过敏、儿童安全和场次的最终确认。", "product": product_to_dict(product) if product else None, "fallback_used": result.fallback_used}


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
        valid_candidates.append(item)
        match_meta[item.id] = (children_match, weather_match, interest_match, score)
    payload = {
        "adult_count": request.adult_count,
        "child_count": request.child_count,
        "child_ages": request.child_ages,
        "budget": str(request.budget),
        "weather": request.weather,
        "interests": request.interests,
        "natural_language": request.natural_language,
        "dietary_restrictions": request.dietary_restrictions,
        "allergy_information": request.allergy_information,
        "products": [{"id": item.id, "product_name": item.product_name, "sale_quantity": item.sale_quantity} for item in valid_candidates],
    }
    agent_result = AgentOrchestrator(db).match_visitor(payload)
    output = agent_result.value
    output_ids = set(output.selected_product_ids)
    results = []
    for item in sorted(valid_candidates, key=lambda product: match_meta[product.id][3], reverse=True):
        children_match, weather_match, interest_match, score = match_meta[item.id]
        reason = output.reasons.get(str(item.id), item.recommendation_reason)
        results.append({
            "product": product_to_dict(item),
            "score": score + (3 if item.id in output_ids else 0),
            "recommendation_reason": reason,
            "budget_match": item.suggested_price <= request.budget,
            "children_match": children_match,
            "weather_match": weather_match,
            "interest_match": interest_match,
            "schedule": output.schedule_notes.get(str(item.id)) or build_schedule(db, item, request.arrival_time, request.preferred_experience_time),
            "limited_adjustments": output.limited_adjustments.get(str(item.id)) or ["预约意向中可备注希望的体验场次", "实时名额变化后以酒店与商户确认结果为准"],
            "allergy_warning": output.allergy_warning or None,
        })
    return {"results": results, "trace_id": agent_result.trace_id, "fallback_used": agent_result.fallback_used, "interpreted_needs": interpreted_needs}


@router.post("/intents")
def create_intent(request: VisitorIntentCreate, db: Session = Depends(get_db)):
    product = get_product(db, request.product_id)
    if not product or product.status not in {"ON_SALE", "LOW_STOCK"} or product.sale_quantity <= 0:
        raise AppError("PRODUCT_UNAVAILABLE", "当前套餐已无法提交预约意向", retryable=True)
    if request.child_count != len(request.child_ages):
        raise AppError("VALIDATION_ERROR", "儿童人数与儿童年龄数量不一致", field="child_ages")
    result = {
        "product_id": product.id,
        "product_name": product.product_name,
        "submitted_price": str(product.suggested_price),
        "submitted_quantity": product.sale_quantity,
        "allergy_information": request.allergy_information,
    }
    intent = VisitorIntent(**request.model_dump(), recommendation_result=result, intent_status="NEW")
    db.add(intent)
    db.commit()
    db.refresh(intent)
    phone = intent.contact_phone
    masked = phone[:3] + "****" + phone[-4:] if len(phone) >= 7 else "***"
    return {"id": intent.id, "product_id": intent.product_id, "intent_status": intent.intent_status, "contact_phone_masked": masked, "message": "预约意向已提交，酒店会根据资源实时状态联系确认。"}


@router.get("/public-resources")
def public_resources(db: Session = Depends(get_db), weather: str = "RAIN"):
    items = list(db.scalars(select(PublicResource).where(PublicResource.status == "ACTIVE").order_by(PublicResource.id)).all())
    return [{"id": item.id, "resource_name": item.resource_name, "category": item.category, "description": item.description, "address": item.address, "opening_hours": item.opening_hours, "weather_supported": is_weather_supported(item.weather_tags, weather), "source": item.source} for item in items]
