"""Authenticated, narrow business tools exposed to the OpenClaw plugin.

The Feishu channel reaches the same ``stayscape-main`` Agent, but it does not
inherit the browser's FastAPI context.  These endpoints are the only bridge
from the plugin back to StayScape business data.  They deliberately expose no
SQL, shell or arbitrary HTTP. Product creation and publishing remain gated by
FastAPI validation and an explicit allowlisted hotel-operator confirmation.
"""

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ...agent.context import RequestContext
from ...config import settings
from ...core.exceptions import AppError
from ...db import get_db
from ...models import AgentApiToken, Hotel, HotelService, Merchant, PartnerResource, RoomInventory, TravelProduct, User
from ...repositories.product_repository import list_products
from ...schemas.products import GenerateProductRequest
from ...services.product_proposal_service import ProductProposalService
from ...services.operations_insight_service import OperationsInsightService
from ...services.knowledge_service import KnowledgeService
from ...services.hotel_opportunity_service import HotelOpportunityService
from ...services.product_service import ProductService
from ...services.weather_service import WeatherService
from ...services.agent_token_service import resolve_read_token
from ...services.serializers import product_to_dict

router = APIRouter(prefix="/agent-tools", tags=["agent-tools"])


class AgentProductSearchRequest(BaseModel):
    target_date: date | None = None
    target_crowd: str | None = Field(default=None, max_length=60)
    weather: str | None = Field(default=None, max_length=30)
    budget: Decimal | None = Field(default=None, gt=0)
    query: str | None = Field(default=None, max_length=160)
    limit: int = Field(default=20, ge=1, le=50)


class AgentProductGenerateRequest(BaseModel):
    """Natural-language brief for a bounded, pending product candidate."""

    natural_language: str = Field(min_length=2, max_length=800)
    conversation_id: str | None = Field(default=None, max_length=120)
    variant_count: int = Field(default=1, ge=1, le=3)


def _agent_api_token(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> AgentApiToken:
    raw = authorization.removeprefix("Bearer ").strip() if authorization else None
    return resolve_read_token(db, raw)


def _agent_owner(db: Session, token: AgentApiToken) -> tuple[User, Hotel]:
    user = db.get(User, token.user_id)
    hotel = db.get(Hotel, token.hotel_id)
    if not user or user.status != "ACTIVE" or user.role != "HOTEL" or not hotel or hotel.status != "ACTIVE":
        raise AppError("AGENT_TOKEN_INVALID", "Agent Token 绑定的账号或酒店已停用", status_code=401)
    return user, hotel


@router.get("/me")
def agent_me(token: AgentApiToken = Depends(_agent_api_token), db: Session = Depends(get_db)):
    """Connection probe for an external ClawHive chat Skill."""
    user, hotel = _agent_owner(db, token)
    db.commit()
    return {
        "connected": True,
        "token_name": token.name,
        "user": {"id": user.id, "username": user.username, "role": user.role},
        "hotel": {"id": hotel.id, "name": hotel.name, "city": hotel.city},
        "read_only": False,
        "permissions": ["visitor_products_read", "product_proposals_generate"],
        "write_actions": [],
        "last_used_at": token.last_used_at,
    }


@router.post("/visitor/products/search")
def search_agent_products(
    request: AgentProductSearchRequest,
    token: AgentApiToken = Depends(_agent_api_token),
    db: Session = Depends(get_db),
):
    """Return only sellable public products for the hotel bound to the token."""
    from ...api.v1.visitor import safe_product_context

    _, hotel = _agent_owner(db, token)
    products = list_products(db, hotel_id=token.hotel_id, public_only=True)
    needle = str(request.query or "").strip().lower()
    if request.target_date:
        products = [item for item in products if item.target_date == request.target_date]
    if request.target_crowd:
        crowd = request.target_crowd.strip().upper()
        products = [item for item in products if str(item.target_crowd or "").upper() in {crowd, "ALL"}]
    if request.budget is not None:
        products = [item for item in products if item.suggested_price <= request.budget]
    if needle:
        products = [
            item for item in products
            if needle in f"{item.product_name} {item.theme} {item.target_crowd}".lower()
            or any(needle in str(row.resource_name or "").lower() for row in item.resources)
        ]
    products = [item for item in products if item.sale_quantity > 0 and item.status in {"ON_SALE", "LOW_STOCK"}]
    products = products[: request.limit]
    result = {"hotel_id": token.hotel_id, "items": [safe_product_context(db, item) for item in products], "count": len(products)}
    db.commit()
    return result


def _agent_candidate_view(db: Session, proposal) -> dict[str, Any]:
    """Expose the same factual product card used by the hotel workbench."""
    product = db.get(TravelProduct, proposal.product_id)
    if product is None:
        raise AppError("PROPOSAL_PRODUCT_INVALID", "生成的产品候选不存在", status_code=409)
    data = product_to_dict(product)
    room = db.get(RoomInventory, product.room_inventory_id)
    insight = proposal.insight_snapshot or {}
    weather = proposal.weather_snapshot or {}
    reasons: list[str] = []
    evidence: list[dict[str, Any]] = []
    if room:
        reasons.append(f"{room.room_type}当天还剩{room.available_count}间，可承载{product.party_size}人。")
        evidence.append({"type": "INVENTORY", "label": room.room_type, "value": int(room.available_count or 0), "unit": "间"})
    top_crowds = insight.get("top_crowds") or []
    crowd_hit = next((item for item in top_crowds if str(item.get("target_crowd")) == str(product.target_crowd)), None)
    if crowd_hit:
        reasons.append(f"近14天{product.target_crowd}客群确认订单最多，适合优先验证这一方向。")
        evidence.append({"type": "DEMAND", "label": product.target_crowd, "value": int(crowd_hit.get("confirmed_orders") or 0), "unit": "笔确认订单"})
    elif insight.get("confirmed_order_count"):
        reasons.append(f"已查询近14天经营汇总，当前按{product.target_crowd}客群生成候选。")
    for row in product.resources:
        if row.resource_type == "PARTNER_RESOURCE":
            resource = db.get(PartnerResource, row.resource_id)
            if resource:
                capacity = int(resource.remaining_capacity or 0)
                reasons.append(f"{resource.resource_name}剩余{capacity}个名额，每套消耗{row.quantity_per_package}个，容量可支撑约{max(0, capacity // max(1, row.quantity_per_package))}套。")
                evidence.append({"type": "CAPACITY", "label": resource.resource_name, "value": capacity, "per_package": row.quantity_per_package, "unit": "个名额"})
        elif row.resource_type == "HOTEL_SERVICE":
            service = db.get(HotelService, row.resource_id)
            if service:
                evidence.append({"type": "SERVICE", "label": service.service_name, "value": int(service.available_quantity or 0), "unit": "份"})
    if weather.get("verification_status") == "ACTIVE":
        reasons.append(str(weather.get("advisory") or f"{product.weather}天气适配已核验。"))
    else:
        reasons.append("天气信息尚未达到 ACTIVE 核验状态，已保留为需确认风险。")
    data["proposal_id"] = proposal.id
    data["status"] = "PENDING_CONFIRMATION"
    data["why_recommended"] = reasons[:6]
    data["evidence"] = evidence
    data["operation_conclusion"] = f"优先验证{product.target_date}的{product.room_inventory_id and (room.room_type if room else '当前房型')}：确定性校验后最多可售{product.sale_quantity}套，瓶颈为{product.bottleneck_resource or '组合资源'}。"
    data["validation"] = {
        "status": "PASSED",
        "checks": ["实时库存与资源", "容量", "时间冲突", "天气适配", "最低利润"],
        "bottleneck_resource": product.bottleneck_resource,
        "sale_quantity": product.sale_quantity,
        "unit_cost": product.unit_cost,
        "minimum_allowed_price": product.minimum_allowed_price,
        "suggested_price": product.suggested_price,
        "gross_profit": product.gross_profit,
        "gross_margin": product.gross_margin,
    }
    data["weather_context"] = weather
    data["operations_insights"] = insight
    return data


@router.post("/hotel/products/generate")
def generate_agent_product(
    request: AgentProductGenerateRequest,
    token: AgentApiToken = Depends(_agent_api_token),
    db: Session = Depends(get_db),
):
    """Generate database-backed pending candidates without publishing them."""
    user, hotel = _agent_owner(db, token)
    context = RequestContext(
        source_channel="CLAWHIVE",
        actor_role="HOTEL_OPERATOR",
        hotel_id=hotel.id,
        user_id=user.id,
        conversation_id=request.conversation_id or f"agent-token-{token.id}",
    )
    service = ProductProposalService(db, hotel.id, context)
    conversation = service.conversation(
        external_id=request.conversation_id or f"agent-token-{token.id}",
        title="ClawHive 文旅产品生成",
    )
    proposals = service.create_from_language(
        request.natural_language,
        conversation=conversation,
        variant_count=request.variant_count,
    )
    db.commit()
    items = [_agent_candidate_view(db, proposal) for proposal in proposals]
    return {
        "status": "PENDING_CONFIRMATION",
        "hotel": {"id": hotel.id, "name": hotel.name, "city": hotel.city},
        "items": items,
        "count": len(items),
        "message": "已结合当前酒店数据库、库存、资源、天气和近14天经营汇总生成待确认候选；候选不会自动发布，请在酒店工作台确认。",
        "human_confirmation_required": True,
    }


class ToolRequest(BaseModel):
    hotel_id: int = Field(gt=0)
    payload: dict[str, Any] = Field(default_factory=dict)


def _tool_context(
    authorization: str | None = Header(default=None),
    source_channel: str | None = Header(default=None, alias="X-StayScape-Source-Channel"),
    actor_role_header: str | None = Header(default=None, alias="X-StayScape-Actor-Role"),
    hotel_id: str | None = Header(default=None, alias="X-StayScape-Hotel-Id"),
    sender_id: str | None = Header(default=None, alias="X-StayScape-Sender-Id"),
    direct_message: str | None = Header(default=None, alias="X-StayScape-Feishu-DM"),
    group_id: str | None = Header(default=None, alias="X-StayScape-Feishu-Group-Id"),
    conversation_id: str | None = Header(default=None, alias="X-StayScape-Conversation-Id"),
) -> RequestContext:
    expected = settings.stayscape_agent_tool_token
    if not expected or authorization != f"Bearer {expected}":
        raise AppError("AGENT_TOOL_UNAUTHORIZED", "Agent Tool authentication failed", status_code=401)
    if not (settings.feishu_enabled and settings.feishu_app_id and settings.feishu_app_secret):
        raise AppError("FEISHU_DISABLED", "Feishu business tools are disabled", status_code=403)
    if source_channel != "FEISHU" or not hotel_id:
        raise AppError("AGENT_TOOL_CONTEXT_REQUIRED", "Missing a trusted Feishu source or hotel context", status_code=403)
    if not sender_id:
        raise AppError("FEISHU_SENDER_FORBIDDEN", "The Feishu runtime did not provide a sender identity", status_code=403)
    def _csv(value: str) -> set[str]:
        return {item.strip() for item in value.split(",") if item.strip()}

    dm_senders = _csv(settings.feishu_dm_allow_from)
    group_ids = {item.strip() for item in settings.feishu_group_allow_from.split(",") if item.strip()}
    operator_senders = _csv(settings.feishu_operator_allow_from)
    support_senders = _csv(settings.feishu_support_allow_from)
    # Backwards-compatible demo configuration: when role-specific lists are
    # absent, the existing DM allowlist is treated as operator-only. In live
    # deployments role-specific lists are recommended and are authoritative.
    if not operator_senders and not support_senders:
        operator_senders = set(dm_senders)
    configured_group_senders = _csv(settings.feishu_group_sender_allow_from)
    # The channel allowlists remain the first boundary. Role lists only assign
    # the trusted StayScape role after the sender has passed that boundary.
    # When role-specific lists are absent, the legacy/demo DM list is mapped to
    # HOTEL_OPERATOR above; group sender access still requires its own list.
    if direct_message == "true":
        allowed = sender_id in dm_senders
    elif group_id:
        allowed = group_id in group_ids and sender_id in configured_group_senders
    else:
        allowed = False
    if not allowed:
        raise AppError("FEISHU_SENDER_FORBIDDEN", "The Feishu sender is not on the business tool allowlist", status_code=403)
    if sender_id in operator_senders:
        trusted_actor_role = "HOTEL_OPERATOR"
    elif sender_id in support_senders:
        trusted_actor_role = "HOTEL_SUPPORT"
    else:
        raise AppError("FEISHU_ROLE_FORBIDDEN", "The Feishu sender has no assigned StayScape role", status_code=403)
    if actor_role_header and actor_role_header != trusted_actor_role:
        raise AppError("FEISHU_ROLE_MISMATCH", "The supplied actor role does not match the sender allowlist", status_code=403)
    try:
        parsed_hotel_id = int(hotel_id)
    except (TypeError, ValueError) as exc:
        raise AppError("AGENT_TOOL_CONTEXT_INVALID", "The hotel context is invalid", status_code=403) from exc
    return RequestContext(
        source_channel="FEISHU",
        actor_role=trusted_actor_role,
        hotel_id=parsed_hotel_id,
        conversation_id=conversation_id,
    )


def _hotel_or_404(db: Session, hotel_id: int) -> Hotel:
    hotel = db.get(Hotel, hotel_id)
    if not hotel or hotel.status != "ACTIVE":
        raise AppError("HOTEL_NOT_FOUND", "The hotel does not exist or is inactive", status_code=404)
    return hotel


def _assert_hotel_context(context: RequestContext, hotel_id: int) -> None:
    if context.hotel_id != hotel_id:
        raise AppError("AGENT_TOOL_CONTEXT_INVALID", "The request hotel differs from the trusted context", status_code=403)


def _partner_resource_context(resource: PartnerResource) -> dict[str, Any]:
    """Return only the operational fields a Feishu Agent needs to plan a draft.

    Settlement and market prices stay inside FastAPI's deterministic pricing
    boundary.  The Agent can select a resource by its public operating
    attributes; it must never become the source of truth for cost or price.
    """
    return {
        "id": resource.id,
        "merchant_id": resource.merchant_id,
        "merchant_name": resource.merchant.merchant_name if resource.merchant else None,
        "resource_name": resource.resource_name,
        "category": resource.category,
        "description": resource.description,
        "available_date": resource.available_date,
        "start_time": resource.start_time,
        "end_time": resource.end_time,
        "remaining_capacity": resource.remaining_capacity,
        "suitable_crowds": resource.suitable_crowds,
        "minimum_age": resource.minimum_age,
        "maximum_age": resource.maximum_age,
        "indoor": resource.indoor,
        "weather_tags": resource.weather_tags,
        "address": resource.address,
        "booking_notice": resource.booking_notice,
        "package_enabled": resource.package_enabled,
        "source_type": resource.source_type,
        "status": resource.status,
    }


def _draft_summary(product) -> dict[str, Any]:
    """Keep Feishu's write response useful without leaking internal accounting."""
    return {
        "id": product.id,
        "product_name": product.product_name,
        "marketing_title": product.marketing_title,
        "theme": product.theme,
        "target_crowd": product.target_crowd,
        "weather": product.weather,
        "target_date": product.target_date,
        "sale_quantity": product.sale_quantity,
        "suggested_price": str(product.suggested_price),
        "status": product.status,
        "resources": [
            {
                "resource_type": item.resource_type,
                "resource_id": item.resource_id,
                "resource_name": item.resource_name,
                "quantity_per_package": item.quantity_per_package,
                "available_date": getattr(item, "available_date", None),
                "start_time": getattr(item, "start_time", None),
                "end_time": getattr(item, "end_time", None),
            }
            for item in product.resources
        ],
    }


@router.post("/hotel-context")
def hotel_context(
    request: ToolRequest,
    context: RequestContext = Depends(_tool_context),
    db: Session = Depends(get_db),
):
    _assert_hotel_context(context, request.hotel_id)
    _hotel_or_404(db, request.hotel_id)
    rooms = list(
        db.scalars(
            select(RoomInventory)
            .where(RoomInventory.hotel_id == request.hotel_id)
            .order_by(RoomInventory.available_date, RoomInventory.id)
        ).all()
    )
    services = list(
        db.scalars(
            select(HotelService)
            .where(HotelService.hotel_id == request.hotel_id)
            .order_by(HotelService.available_date, HotelService.id)
        ).all()
    )
    resources = list(
        db.scalars(
            select(PartnerResource)
            .join(Merchant)
            .where(Merchant.hotel_id == request.hotel_id)
            .order_by(PartnerResource.available_date, PartnerResource.id)
        ).all()
    )
    return {
        "hotel_id": request.hotel_id,
        "rooms": [
            {
                "id": item.id,
                "room_type": item.room_type,
                "available_date": item.available_date,
                "available_count": item.available_count,
                "max_guests": item.max_guests,
                "suitable_crowds": item.suitable_crowds,
                "tags": item.tags,
                "status": item.status,
            }
            for item in rooms
        ],
        "services": [
            {
                "id": item.id,
                "service_name": item.service_name,
                "service_type": item.service_type,
                "available_date": item.available_date,
                "available_quantity": item.available_quantity,
                "start_time": item.start_time,
                "end_time": item.end_time,
                "status": item.status,
                "suitable_crowds": item.suitable_crowds,
            }
            for item in services
        ],
        "partner_resources": [_partner_resource_context(item) for item in resources],
        "source_channel": context.source_channel,
        "actor_role": context.actor_role,
    }


@router.post("/available-products")
def available_products(
    request: ToolRequest,
    context: RequestContext = Depends(_tool_context),
    db: Session = Depends(get_db),
):
    _assert_hotel_context(context, request.hotel_id)
    _hotel_or_404(db, request.hotel_id)
    products = list_products(db, hotel_id=request.hotel_id, public_only=True)
    payload = request.payload
    target_date = payload.get("target_date")
    budget = payload.get("budget")
    if target_date:
        products = [item for item in products if item.target_date and item.target_date.isoformat() == str(target_date)]
    if budget is not None:
        try:
            budget_value = Decimal(str(budget))
            products = [item for item in products if item.suggested_price <= budget_value]
        except (InvalidOperation, TypeError, ValueError):
            raise AppError("VALIDATION_ERROR", "Budget must be a valid number", status_code=422)
    from ...api.v1.visitor import safe_product_context

    return {
        "items": [safe_product_context(db, item) for item in products],
        "source_channel": context.source_channel,
        "actor_role": context.actor_role,
    }


@router.post("/operations-insights")
def operations_insights(
    request: ToolRequest,
    context: RequestContext = Depends(_tool_context),
    db: Session = Depends(get_db),
):
    """Read aggregated sales signals; no guest PII or hidden reasoning."""
    _assert_hotel_context(context, request.hotel_id)
    _hotel_or_404(db, request.hotel_id)
    target_date = request.payload.get("target_date")
    try:
        selected_date = GenerateProductRequest.model_validate({"target_date": target_date or date.today().isoformat()}).target_date
    except Exception as exc:
        raise AppError("VALIDATION_ERROR", "target_date must be an ISO date", field="target_date") from exc
    return OperationsInsightService(db, request.hotel_id).snapshot(target_date=selected_date)


@router.post("/hotel-opportunity")
def hotel_opportunity(
    request: ToolRequest,
    context: RequestContext = Depends(_tool_context),
    db: Session = Depends(get_db),
):
    """Return a fact-only operating brief before an Agent creates candidates.

    This endpoint intentionally has no product write side effect. It gives the
    余宿成景 orchestration Skill an auditable starting point without granting it
    arbitrary filesystem or database access.
    """
    _assert_hotel_context(context, request.hotel_id)
    _hotel_or_404(db, request.hotel_id)
    payload = request.payload
    raw_date = payload.get("target_date") or date.today().isoformat()
    try:
        target_date = date.fromisoformat(str(raw_date))
        party_size = int(payload.get("party_size") or 0)
        direction_limit = int(payload.get("direction_limit") or 4)
    except (TypeError, ValueError) as exc:
        raise AppError("VALIDATION_ERROR", "target_date、party_size 或 direction_limit 格式无效", status_code=422) from exc
    if party_size < 0 or party_size > 12 or direction_limit < 1 or direction_limit > 8:
        raise AppError("VALIDATION_ERROR", "party_size 或 direction_limit 超出允许范围", status_code=422)
    return HotelOpportunityService(db, request.hotel_id).analyze(
        target_date=target_date,
        target_crowd=str(payload.get("target_crowd") or "").strip()[:60],
        party_size=party_size,
        theme=str(payload.get("theme") or "").strip()[:160],
        knowledge_query=str(payload.get("knowledge_query") or "").strip()[:500],
        direction_limit=direction_limit,
    )


@router.post("/travel-knowledge")
def travel_knowledge(
    request: ToolRequest,
    context: RequestContext = Depends(_tool_context),
    db: Session = Depends(get_db),
):
    _assert_hotel_context(context, request.hotel_id)
    _hotel_or_404(db, request.hotel_id)
    payload = request.payload
    items = KnowledgeService(db).search(
        str(payload.get("query") or ""),
        target_crowd=str(payload.get("target_crowd") or ""),
        weather=str(payload.get("weather") or ""),
        limit=min(12, max(1, int(payload.get("limit") or 8))),
    )
    return {
        "items": items,
        "notice": "知识库仅提供带来源的参考信息；未确认项不可作为已预约或可售资源承诺。",
    }


def _create_product_proposal(
    request: ToolRequest,
    context: RequestContext,
    db: Session,
):
    _assert_hotel_context(context, request.hotel_id)
    if context.actor_role != "HOTEL_OPERATOR":
        raise AppError("FORBIDDEN", "Only an allowlisted hotel operator can create a product proposal", status_code=403)
    try:
        payload = dict(request.payload)
        natural_language = str(payload.pop("natural_language", "")).strip()
        generate_request = GenerateProductRequest.model_validate(payload) if payload else None
    except Exception as exc:
        raise AppError("VALIDATION_ERROR", "Product proposal parameters are invalid", details=str(exc)) from exc
    if generate_request is None and not natural_language:
        raise AppError("VALIDATION_ERROR", "请提供 natural_language 或完整的产品候选参数。", field="payload")
    service = ProductProposalService(db, request.hotel_id, context)
    conversation = service.conversation(external_id=context.conversation_id or "", title="飞书酒店 AI 运营任务")
    proposals = (
        service.create_from_language(natural_language, conversation=conversation)
        if natural_language and generate_request is None
        else service.create_from_request(generate_request, conversation=conversation, natural_language=natural_language)
    )
    db.commit()
    return {
        "conversation_id": conversation.id,
        "proposal_ids": [item.id for item in proposals],
        "proposals": [
            {
                "proposal_id": item.id,
                "status": item.status,
                "product": _draft_summary(db.get(TravelProduct, item.product_id)),
                "trace_ids": item.trace_ids,
                "execution_steps": item.execution_steps,
            }
            for item in proposals
        ],
        "message": "候选尚未加入草稿或发布。请明确确认：加入草稿，或确认发布第 N 个候选。",
        "web_url": "/hotel/products",
    }


@router.post("/product-proposal")
def create_product_proposal(
    request: ToolRequest,
    context: RequestContext = Depends(_tool_context),
    db: Session = Depends(get_db),
):
    return _create_product_proposal(request, context, db)


@router.post("/product-draft")
def create_product_draft_legacy(
    request: ToolRequest,
    context: RequestContext = Depends(_tool_context),
    db: Session = Depends(get_db),
):
    """Compatibility path; intentionally returns a pending proposal, not a draft."""
    return _create_product_proposal(request, context, db)


@router.post("/proposal-confirm")
def confirm_product_proposal(
    request: ToolRequest,
    context: RequestContext = Depends(_tool_context),
    db: Session = Depends(get_db),
):
    _assert_hotel_context(context, request.hotel_id)
    if context.actor_role != "HOTEL_OPERATOR":
        raise AppError("FORBIDDEN", "Only an allowlisted hotel operator can confirm a product proposal", status_code=403)
    try:
        proposal_id = int(request.payload.get("proposal_id"))
        action = str(request.payload.get("action") or "").upper()
    except (TypeError, ValueError) as exc:
        raise AppError("VALIDATION_ERROR", "proposal_id and action are required", status_code=422) from exc
    proposal = ProductProposalService(db, request.hotel_id, context).confirm(
        proposal_id,
        action=action,
        confirmed_by=f"feishu:{context.conversation_id or 'operator'}",
    )
    db.commit()
    product = db.get(TravelProduct, proposal.product_id)
    return {
        "proposal_id": proposal.id,
        "status": proposal.status,
        "product": _draft_summary(product),
        "message": "已发布并再次完成实时库存复核。" if action == "PUBLISH" else "已加入酒店草稿，尚未对游客展示。",
    }


@router.post("/product-health-check")
def product_health_check(
    request: ToolRequest,
    context: RequestContext = Depends(_tool_context),
    db: Session = Depends(get_db),
):
    """Revalidate products after an operator asks about weather/resource change.

    This is an explicit operator action. The service may reduce quantity,
    replace an allowed partner resource, or pause a product, but it never
    creates or publishes a new one.
    """
    _assert_hotel_context(context, request.hotel_id)
    _hotel_or_404(db, request.hotel_id)
    if context.actor_role != "HOTEL_OPERATOR":
        raise AppError("FORBIDDEN", "Only an allowlisted hotel operator can recheck product health", status_code=403)
    payload = request.payload
    raw_date = payload.get("target_date")
    product_id = payload.get("product_id")
    try:
        selected_date = date.fromisoformat(str(raw_date)) if raw_date else None
        selected_product_id = int(product_id) if product_id is not None else None
    except (TypeError, ValueError) as exc:
        raise AppError("VALIDATION_ERROR", "target_date 或 product_id 格式无效", status_code=422) from exc
    query = (
        select(TravelProduct)
        .where(
            TravelProduct.hotel_id == request.hotel_id,
            TravelProduct.status.not_in({"DELETED", "PENDING_CONFIRMATION"}),
        )
        .options(selectinload(TravelProduct.resources))
        .order_by(TravelProduct.target_date, TravelProduct.id)
    )
    if selected_date:
        query = query.where(TravelProduct.target_date == selected_date)
    if selected_product_id:
        query = query.where(TravelProduct.id == selected_product_id)
    products = list(db.scalars(query).unique().all())
    if selected_product_id and not products:
        raise AppError("NOT_FOUND", "产品不存在或不属于当前酒店", status_code=404)
    dates = sorted({item.target_date for item in products})
    forecasts = {
        item.isoformat(): WeatherService(db).get_forecast(
            "杭州",
            item,
            force_refresh=bool(payload.get("refresh_weather")),
        )
        for item in dates
    }
    service = ProductService(db, request.hotel_id)
    affected: list[dict[str, Any]] = []
    for product in products:
        forecast = forecasts[product.target_date.isoformat()]
        weather_updated = False
        if forecast.get("usable") and product.weather != str(forecast.get("scenario") or product.weather):
            product.weather = str(forecast.get("scenario"))
            weather_updated = True
        adjustment = service.recalculate_product(product)
        affected.append(
            {
                "product_id": product.id,
                "product_name": product.product_name,
                "weather_updated": weather_updated,
                "weather_status": forecast.get("verification_status"),
                "action": adjustment.get("action"),
                "status": adjustment.get("status"),
                "new_quantity": adjustment.get("new_quantity"),
                "reason": adjustment.get("reason"),
            }
        )
    db.commit()
    return {
        "target_date": selected_date.isoformat() if selected_date else None,
        "weather": forecasts,
        "items": affected,
        "message": "已按当前事实重新计算；若天气信息需确认，未将其当作已确认天气自动替换。",
    }
