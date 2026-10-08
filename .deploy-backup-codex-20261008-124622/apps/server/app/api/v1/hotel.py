from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, File, Query, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from ...core.exceptions import AppError
from ...core.security import create_websocket_ticket
from ...config import settings
from ...db import get_db
from ...models import AgentApiToken, AgentConversation, Hotel, HotelService, Merchant, PartnerResource, ProductProposal, ProductResource, ResourceChangeEvent, RoomInventory, SkillCallLog, TravelProduct, User, VisitorIntent
from ...repositories.product_repository import get_product, get_products_for_serialization, list_products, list_products_for_serialization
from ...repositories.resource_repository import list_partner_resources, list_rooms, list_services
from ...schemas.dashboard import DashboardResponse
from ...schemas.products import AdjustmentRead, BatchMarketingRefinementRequest, CopyRewriteRequest, GenerateProductRequest, MarketingRegenerationRequest, ProductBatchApplyRequest, ProductDetailResponse, ProductDraftInterpretRequest, ProductDraftInterpretResponse, ProductGenerateResponse, ProductListResponse, ProductRead, ProductRefineRequest, ProductRefineResponse, ProductStatusRequest, ProductUpdateRequest, ResourceChangeResponse
from ...schemas.ai_operations import AssistantConversationCreate, AssistantMessageCreate, AgentConversationRead, AssistantTaskResponse, ProductProposalRead, ProposalConfirmRequest
from ...schemas.ai_operations import OrderOverviewResponse, SalesCommandRequest, SalesCommandResponse, OperationsQueryRequest
from ...schemas.visitor import VisitorIntentStatusUpdate
from ...schemas.resources import MediaImportRequest, MediaSearchRequest, MerchantRead, PackageToggleRequest, PartnerResourceCreate, PartnerResourceRead, PartnerResourceUpdate, ResourceAddressUpdate, ResourceMediaUpdate, RoomCreate, RoomRead, RoomUpdate, ServiceCreate, ServiceRead, ServiceUpdate
from ...services.product_service import ProductService
from ...services.product_refine_service import ProductRefiner
from ...services.sales_command_service import CATEGORY_KEYWORDS, apply_sales_command
from ...services.product_advisor_service import ProductAdvisor
from ...services.integration_settings_service import public_settings, save_settings
from ...schemas.ai_operations import AdvisorRequest, AdvisorResponse
from ...services.product_proposal_service import ProductProposalService
from ...services.product_draft_parser import interpret_product_draft
from ...services.operations_insight_service import OperationsInsightService
from ...services.knowledge_service import KnowledgeService
from ...services.weather_service import WeatherService
from ...services.inventory_service import release_intent_inventory, reconcile_published_capacity, sweep_expired_intents
from ...services.serializers import build_product_resource_cache, partner_resource_to_dict, product_to_dict
from ...services.public_copy import visitor_product_to_dict
from ...services.media_library_service import MAX_MEDIA_BYTES, MediaLibraryService
from ...services.agent_token_service import create_token, list_tokens, revoke_token
from ...agent.openclaw import OpenClawAgent
from ...agent.context import RequestContext
from ..deps import get_hotel_user, resolve_hotel_id
from ..websocket_manager import manager

router = APIRouter(prefix="/hotel", tags=["hotel"])


class HotelPartnerResourceCreate(PartnerResourceCreate):
    """Hotel-side resource entry; the merchant must belong to this hotel."""

    merchant_id: int = Field(gt=0)


class KnowledgeVerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reviewed_fields: list[str] = Field(min_length=15, max_length=15)
    review_note: str = Field(min_length=8, max_length=1000)


class AgentTokenCreateRequest(BaseModel):
    name: str = Field(default="ClawHive 只读接入", min_length=1, max_length=120)


class IntegrationSettingsUpdate(BaseModel):
    """Allow only documented runtime settings; credentials remain env-only."""

    model_config = ConfigDict(extra="forbid")

    agent_provider: str | None = Field(default=None, max_length=40)
    openclaw_base_url: str | None = Field(default=None, max_length=500)
    primary_model: str | None = Field(default=None, max_length=160)
    reasoning_provider: str | None = Field(default=None, max_length=60)
    deepseek_api_key: str | None = Field(default=None, max_length=500)
    vision_provider: str | None = Field(default=None, max_length=60)
    vision_api_key: str | None = Field(default=None, max_length=500)
    image_model: str | None = Field(default=None, max_length=160)
    image_api_key: str | None = Field(default=None, max_length=500)
    image_workspace_id: str | None = Field(default=None, max_length=160)
    image_enabled: bool | None = None
    hotel_address: str | None = Field(default=None, min_length=4, max_length=255)


def _agent_token_view(row: AgentApiToken) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "is_active": row.is_active,
        "created_at": row.created_at,
        "last_used_at": row.last_used_at,
    }


@router.post("/ws-ticket")
def create_hotel_ws_ticket(db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    """Exchange the normal API JWT for a one-minute, hotel-scoped WS ticket."""
    return {"ticket": create_websocket_ticket(user_id=user.id, hotel_id=hotel_id_for(db, user)), "expires_in": 60}


@router.get("/agent-tokens")
def get_agent_tokens(db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    hotel_id = hotel_id_for(db, user)
    return {"items": [_agent_token_view(item) for item in list_tokens(db, user=user, hotel_id=hotel_id)]}


@router.post("/agent-tokens")
def create_agent_token(request: AgentTokenCreateRequest, db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    hotel_id = hotel_id_for(db, user)
    row, raw = create_token(db, user=user, hotel_id=hotel_id, name=request.name)
    db.commit()
    db.refresh(row)
    return {"token": raw, "item": _agent_token_view(row), "notice": "完整 Token 仅显示这一次，请立即复制并保存。"}


@router.post("/agent-tokens/{token_id}/revoke")
def revoke_agent_token(token_id: int, db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    hotel_id = hotel_id_for(db, user)
    row = revoke_token(db, user=user, hotel_id=hotel_id, token_id=token_id)
    db.commit()
    return {"item": _agent_token_view(row), "revoked": True}


def hotel_id_for(db: Session, user: User) -> int:
    return resolve_hotel_id(db, user)


def proposal_to_dict(
    db: Session,
    proposal: ProductProposal,
    *,
    product: TravelProduct | None = None,
    resource_cache: dict | None = None,
    include_marketing_assets: bool = True,
) -> dict:
    """Serialize only auditable task state, never an Agent reasoning trace."""
    if product is None:
        product = get_product(db, proposal.product_id)
    return {
        "id": proposal.id,
        "hotel_id": proposal.hotel_id,
        "conversation_id": proposal.conversation_id,
        "product_id": proposal.product_id,
        "source_channel": proposal.source_channel,
        "status": proposal.status,
        "trace_ids": proposal.trace_ids or [],
        "insight_snapshot": proposal.insight_snapshot,
        "weather_snapshot": proposal.weather_snapshot,
        "knowledge_snapshot": proposal.knowledge_snapshot or [],
        "execution_steps": proposal.execution_steps or [],
        "confirmation_action": proposal.confirmation_action,
        "confirmed_by": proposal.confirmed_by,
        "confirmed_at": proposal.confirmed_at,
        "created_at": proposal.created_at,
        "updated_at": proposal.updated_at,
        "product": product_to_dict(product, resource_cache=resource_cache, include_marketing_assets=include_marketing_assets) if product else None,
    }


def _product_resource_cache(db: Session, hotel_id: int, products: list[TravelProduct]) -> dict:
    # Shared implementation also serves the visitor product serializer.
    return build_product_resource_cache(db, products)


def _hotel_conversation_or_404(db: Session, hotel_id: int, conversation_id: int) -> AgentConversation:
    conversation = db.scalar(select(AgentConversation).where(AgentConversation.id == conversation_id, AgentConversation.hotel_id == hotel_id))
    if not conversation:
        raise AppError("NOT_FOUND", "AI 运营任务不存在", status_code=404)
    return conversation


@router.post("/ai/conversations", response_model=AgentConversationRead)
def create_ai_conversation(request: AssistantConversationCreate, db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    hotel_id = hotel_id_for(db, user)
    service = ProductProposalService(db, hotel_id, RequestContext(source_channel="WEB_HOTEL", actor_role="HOTEL_OPERATOR", hotel_id=hotel_id, user_id=user.id))
    conversation = service.conversation(title=request.title)
    db.commit()
    db.refresh(conversation)
    return conversation


@router.get("/ai/conversations", response_model=list[AgentConversationRead])
def ai_conversations(
    limit: int = Query(default=1, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_hotel_user),
):
    hotel_id = hotel_id_for(db, user)
    return list(db.scalars(
        select(AgentConversation)
        .where(AgentConversation.hotel_id == hotel_id)
        .order_by(AgentConversation.updated_at.desc())
        .limit(limit)
    ).all())


@router.get("/ai/conversations/{conversation_id}", response_model=AgentConversationRead)
def ai_conversation(conversation_id: int, db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    return _hotel_conversation_or_404(db, hotel_id_for(db, user), conversation_id)


@router.post("/ai/conversations/{conversation_id}/messages", response_model=AssistantTaskResponse)
def ai_conversation_message(conversation_id: int, request: AssistantMessageCreate, db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    hotel_id = hotel_id_for(db, user)
    conversation = _hotel_conversation_or_404(db, hotel_id, conversation_id)
    context = RequestContext(source_channel="WEB_HOTEL", actor_role="HOTEL_OPERATOR", hotel_id=hotel_id, user_id=user.id, conversation_id=str(conversation.id))
    proposals = ProductProposalService(db, hotel_id, context).create_from_language(request.natural_language, conversation=conversation)
    db.commit()
    db.refresh(conversation)
    products = get_products_for_serialization(db, [item.product_id for item in proposals], hotel_id)
    products_by_id = {item.id: item for item in products}
    resource_cache = _product_resource_cache(db, hotel_id, products)
    return {
        "conversation": conversation,
        "proposals": [
            proposal_to_dict(
                db,
                item,
                product=products_by_id.get(item.product_id),
                resource_cache=resource_cache,
                include_marketing_assets=True,
            )
            for item in proposals
        ],
        "message": "已生成待确认候选；确认后才会进入草稿或对游客发布。",
    }


@router.get("/ai/proposals", response_model=list[ProductProposalRead])
def ai_proposals(
    status: str | None = None,
    conversation_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_hotel_user),
):
    hotel_id = hotel_id_for(db, user)
    context = RequestContext(source_channel="WEB_HOTEL", actor_role="HOTEL_OPERATOR", hotel_id=hotel_id, user_id=user.id)
    proposals = ProductProposalService(db, hotel_id, context).list_proposals(
        status=status, conversation_id=conversation_id
    )
    products = get_products_for_serialization(db, [item.product_id for item in proposals], hotel_id)
    products_by_id = {item.id: item for item in products}
    resource_cache = _product_resource_cache(db, hotel_id, products)
    return [
        proposal_to_dict(
            db,
            item,
            product=products_by_id.get(item.product_id),
            resource_cache=resource_cache,
            include_marketing_assets=True,
        )
        for item in proposals
    ]


@router.post("/ai/proposals/{proposal_id}/confirm", response_model=ProductProposalRead)
def confirm_ai_proposal(proposal_id: int, request: ProposalConfirmRequest, db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    hotel_id = hotel_id_for(db, user)
    service = ProductProposalService(db, hotel_id, RequestContext(source_channel="WEB_HOTEL", actor_role="HOTEL_OPERATOR", hotel_id=hotel_id, user_id=user.id))
    # 发布前再核验一次最新库存与合作名额；名额变紧就先把最大可售下调，再把结果写进消息里。
    if str(request.action).upper() == "PUBLISH":
        pending = db.get(ProductProposal, proposal_id)
        product = get_product(db, pending.product_id) if pending is not None else None
        if product is not None:
            check = ProductRefiner(db, hotel_id).publish_check(product)
            if int(check["adjusted_quantity"]) < int(check["current_quantity"]):
                product.sale_quantity = int(check["adjusted_quantity"])
                if product.sale_quantity <= 0:
                    product.status = "SOLD_OUT"
                elif product.sale_quantity <= 2:
                    product.status = "LOW_STOCK"
    proposal = service.confirm(proposal_id, action=request.action, confirmed_by=f"web-user:{user.id}")
    db.commit()
    return proposal_to_dict(db, proposal)


@router.get("/ai/overview")
def ai_overview(
    target_date: date | None = None,
    section: str = Query(default="summary"),
    db: Session = Depends(get_db),
    user: User = Depends(get_hotel_user),
):
    """Load only the requested operating-data section."""
    hotel_id = hotel_id_for(db, user)
    selected_date = target_date or date.today()

    if section == "summary":
        day_start = datetime.combine(selected_date, time.min, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        pending_count, pending_today = db.execute(
            select(
                func.count(ProductProposal.id),
                func.count(ProductProposal.id).filter(
                    ProductProposal.created_at >= day_start,
                    ProductProposal.created_at < day_end,
                ),
            ).where(
                ProductProposal.hotel_id == hotel_id,
                ProductProposal.status == "PENDING_CONFIRMATION",
            )
        ).one()
        return {
            "inventory_pressure": OperationsInsightService(db, hotel_id).room_night_pressure(window_days=17),
            "pending_confirmation_count": int(pending_count or 0),
            "pending_today_count": int(pending_today or 0),
        }

    if section == "resources":
        evidence_end = selected_date + timedelta(days=15)
        start_at = datetime.combine(date.today() - timedelta(days=14), time.min, tzinfo=timezone.utc)
        resources = list(db.scalars(
            select(PartnerResource)
            .join(Merchant)
            .options(joinedload(PartnerResource.merchant))
            .where(
                Merchant.hotel_id == hotel_id,
                PartnerResource.available_date >= selected_date,
                PartnerResource.available_date < evidence_end,
            )
            .order_by(PartnerResource.available_date, PartnerResource.resource_name)
        ).all())
        services = list(db.scalars(
            select(HotelService).where(
                HotelService.hotel_id == hotel_id,
                HotelService.available_date >= selected_date,
                HotelService.available_date < evidence_end,
            ).order_by(HotelService.available_date, HotelService.service_name)
        ).all())
        ids = [int(row.id) for row in resources]
        usage = {}
        sales = {}
        if ids:
            usage_rows = db.execute(
                select(ProductResource.resource_id, func.count(func.distinct(ProductResource.product_id)))
                .join(TravelProduct, TravelProduct.id == ProductResource.product_id)
                .where(
                    TravelProduct.hotel_id == hotel_id,
                    ProductResource.resource_type == "PARTNER_RESOURCE",
                    ProductResource.resource_id.in_(ids),
                )
                .group_by(ProductResource.resource_id)
            ).all()
            usage = {int(resource_id): int(count) for resource_id, count in usage_rows}
            sales_rows = db.execute(
                select(ProductResource.resource_id, func.count(func.distinct(VisitorIntent.id)))
                .join(TravelProduct, TravelProduct.id == ProductResource.product_id)
                .join(VisitorIntent, VisitorIntent.product_id == TravelProduct.id)
                .where(
                    TravelProduct.hotel_id == hotel_id,
                    ProductResource.resource_type == "PARTNER_RESOURCE",
                    ProductResource.resource_id.in_(ids),
                    VisitorIntent.reservation_status == "CONFIRMED",
                    or_(VisitorIntent.confirmed_at >= start_at, VisitorIntent.created_at >= start_at),
                )
                .group_by(ProductResource.resource_id)
            ).all()
            sales = {int(resource_id): int(count) for resource_id, count in sales_rows}
        return {
            "operations_insights": {
                "resource_evidence": [{
                    "id": row.id,
                    "name": row.resource_name,
                    "category": row.category,
                    "merchant_name": row.merchant.merchant_name if row.merchant else "",
                    "available_date": row.available_date.isoformat(),
                    "remaining_capacity": int(row.remaining_capacity or 0),
                    "settlement_price": str(row.settlement_price),
                    "market_price": str(row.market_price),
                    "suitable_crowds": row.suitable_crowds,
                    "indoor": bool(row.indoor),
                    "address": row.address,
                    "product_count": usage.get(int(row.id), 0),
                    "recent_confirmed_orders": sales.get(int(row.id), 0),
                    "status": row.status,
                    "package_enabled": bool(row.package_enabled),
                } for row in resources],
                "service_evidence": [{
                    "id": row.id,
                    "name": row.service_name,
                    "type": row.service_type,
                    "available_date": row.available_date.isoformat(),
                    "available_quantity": int(row.available_quantity or 0),
                    "unit_cost": str(row.unit_cost),
                    "reference_price": str(row.reference_price),
                    "suitable_crowds": row.suitable_crowds,
                    "status": row.status,
                } for row in services],
            }
        }

    if section == "weather":
        forecasts = WeatherService(db).get_forecast_range("杭州", selected_date, days=15)
        db.commit()
        selected_weather = next((item for item in forecasts if item.get("target_date") == selected_date.isoformat()), None)
        return {"weather": selected_weather, "weather_forecasts": forecasts}

    if section == "knowledge":
        knowledge = KnowledgeService(db)
        return {"knowledge": knowledge.listing(limit=5000), "knowledge_total": knowledge.total()}

    if section != "full":
        raise AppError("VALIDATION_ERROR", "未知经营数据分类", field="section")

    """One compact, review-friendly view of facts used by hotel AI tasks."""
    day_start = datetime.combine(selected_date, time.min, tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)
    proposal_counts = db.execute(
        select(
            func.count(ProductProposal.id),
            func.count(ProductProposal.id).filter(
                ProductProposal.created_at >= day_start,
                ProductProposal.created_at < day_end,
            ),
        ).where(
            ProductProposal.hotel_id == hotel_id,
            ProductProposal.status == "PENDING_CONFIRMATION",
        )
    ).one()
    pending_count, pending_today = (int(proposal_counts[0] or 0), int(proposal_counts[1] or 0))
    insights = OperationsInsightService(db, hotel_id)
    weather_service = WeatherService(db)
    weather_forecasts = weather_service.get_forecast_range("杭州", selected_date, days=15)
    # get_forecast_range writes refreshed snapshots. Persist this intentional cache
    # from the GET endpoint; otherwise Session.close() rolls it back and every visit
    # calls Open-Meteo again.
    db.commit()
    selected_weather = next((item for item in weather_forecasts if item.get("target_date") == selected_date.isoformat()), None)
    return {
        "operations_insights": insights.snapshot(target_date=selected_date, window_days=15),
        # 顶部指标覆盖演示日期范围（今天至 10 月 15 日，共 17 天）。
        "inventory_pressure": insights.room_night_pressure(window_days=17),
        "weather": selected_weather or weather_service.get_forecast("杭州", selected_date),
        "weather_forecasts": weather_forecasts,
        "knowledge": KnowledgeService(db).listing(limit=5000),
        "knowledge_total": KnowledgeService(db).total(),
        "pending_confirmation_count": pending_count,
        "pending_today_count": pending_today,
        "disclosure": "执行面板只展示可审计步骤与数据来源，不展示模型内部推理。",
    }


@router.post("/ai/conversations/{conversation_id}/clear", response_model=AgentConversationRead)
def clear_ai_conversation(conversation_id: int, db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    """Empty one operating conversation while keeping the task record itself."""

    conversation = _hotel_conversation_or_404(db, hotel_id_for(db, user), conversation_id)
    conversation.messages = []
    conversation.last_execution = None
    db.commit()
    db.refresh(conversation)
    return conversation


@router.delete("/ai/conversations/{conversation_id}")
def delete_ai_conversation(conversation_id: int, db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    conversation = _hotel_conversation_or_404(db, hotel_id_for(db, user), conversation_id)
    # 候选产品通过 conversation_id 引用会话，直接删除会触发外键冲突（500）。
    # 会话只是候选的来源说明，删除会话时保留候选，仅解除来源关联。
    for proposal in db.scalars(select(ProductProposal).where(ProductProposal.conversation_id == conversation.id)).all():
        proposal.conversation_id = None
    db.flush()
    db.delete(conversation)
    db.commit()
    return {"deleted": True, "conversation_id": conversation_id}


@router.get("/settings/integrations")
def hotel_settings(db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    """Current model / image-generation configuration shown in the workbench."""
    hotel = db.get(Hotel, hotel_id_for(db, user))
    return {**public_settings(), "hotel_address": (hotel.address if hotel and hotel.address else "杭州市西湖区")}


@router.put("/settings/integrations")
def update_hotel_settings(payload: IntegrationSettingsUpdate, db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    """Save operator overrides for the model, vision and image services."""
    values = payload.model_dump(exclude_none=True)
    hotel_address = values.pop("hotel_address", None)
    hotel = db.get(Hotel, hotel_id_for(db, user))
    if hotel is not None and hotel_address is not None:
        hotel.address = hotel_address.strip()
        db.commit()
    if values:
        save_settings(values)
    return {**public_settings(), "hotel_address": (hotel.address if hotel and hotel.address else "杭州市西湖区")}


@router.get("/settings/export")
def export_hotel_data(db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    """One-click export of the operating data (local deployment / data safety)."""

    hotel_id = hotel_id_for(db, user)
    hotel = db.get(Hotel, hotel_id)
    products = list_products(db, hotel_id)
    rooms = list_rooms(db, hotel_id)
    resources = list_partner_resources(db, hotel_id)
    intents = list(
        db.scalars(
            select(VisitorIntent).join(TravelProduct).where(TravelProduct.hotel_id == hotel_id)
        ).unique().all()
    )
    knowledge = KnowledgeService(db).listing(limit=200)
    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "hotel": {"id": hotel_id, "name": hotel.name if hotel else "", "city": hotel.city if hotel else ""},
        "settings": public_settings(),
        "rooms": [
            {
                "room_type": item.room_type,
                "available_date": item.available_date.isoformat(),
                "available_count": item.available_count,
                "normal_price": str(item.normal_price),
                "features": item.features,
                "status": item.status,
            }
            for item in rooms
        ],
        "partner_resources": [
            {
                "name": item.resource_name,
                "category": item.category,
                "address": item.address,
                "available_date": item.available_date.isoformat(),
                "remaining_capacity": item.remaining_capacity,
                "settlement_price": str(item.settlement_price),
                "status": item.status,
            }
            for item in resources
        ],
        # Export the same shape the workbench already serves. `visitor_payload`
        # lives in the visitor router; using the serializer here keeps the
        # export decoupled and fixes the previous NameError that broke export.
        "products": [product_to_dict(item) for item in products],
        "orders": [
            {
                "id": item.id,
                "product_id": item.product_id,
                "status": item.reservation_status,
                "contact_name": item.contact_name,
                "contact_phone": item.contact_phone,
                "note": item.other_requirements,
            }
            for item in intents
        ],
        "knowledge": knowledge,
    }


@router.get("/knowledge")
def hotel_knowledge(q: str = "", category: str = "", limit: int = 80, db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    """Read-only view of the文旅知识库 that the Visitor/Product skills quote."""

    _ = user
    service = KnowledgeService(db)
    return {
        "items": service.listing(query=q, category=category, limit=limit),
        "categories": service.categories(),
        "total": service.total(),
        "disclosure": "来源链接检查只反映网页是否可访问，不代表内容真实或仍然有效；访客可见事实须由运营人员逐项对照来源核验。",
    }


@router.post("/knowledge/refresh")
def refresh_hotel_knowledge(db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    """Check source URL reachability without verifying factual content."""

    _ = user
    result = KnowledgeService(db).refresh_sources(city="杭州")
    db.commit()
    return result


@router.post("/knowledge/{item_id}/verify")
def verify_hotel_knowledge(item_id: int, request: KnowledgeVerificationRequest, db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    try:
        item = KnowledgeService(db).review_item(item_id, reviewer_id=user.id, reviewed_fields=request.reviewed_fields, note=request.review_note)
    except LookupError as exc:
        raise AppError(code="KNOWLEDGE_NOT_FOUND", message=str(exc), status_code=404) from exc
    except ValueError as exc:
        raise AppError(code="KNOWLEDGE_REVIEW_INCOMPLETE", message=str(exc), status_code=422) from exc
    db.commit()
    return {"item": item}


@router.post("/products/sales-command", response_model=SalesCommandResponse)
def product_sales_command(request: SalesCommandRequest, db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    """Apply a natural-language pause/resume instruction to matching products."""

    result = apply_sales_command(db, hotel_id_for(db, user), request.natural_language)
    db.commit()
    return result


CROWD_CODE_BY_LABEL = {
    "亲子家庭": "FAMILY",
    "两人约会": "COUPLE",
    "两人同行": "COUPLE",
    "朋友出行": "FRIENDS",
    "朋友相聚": "FRIENDS",
    "独自旅行": "SOLO",
    "一个人慢游": "SOLO",
    "本地周末": "LOCAL_WEEKEND",
    "不限客群": "ALL",
}


@router.post("/ai/conversations/{conversation_id}/advisor", response_model=AdvisorResponse)
def ai_conversation_advisor(
    conversation_id: int,
    request: AdvisorRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_hotel_user),
):
    """One turn of the guided product conversation.

    Every turn reads the database first, explains the recommendation, lists what
    can be adjusted, and only creates real candidates when the operator
    confirms the pending plan.
    """

    hotel_id = hotel_id_for(db, user)
    conversation = _hotel_conversation_or_404(db, hotel_id, conversation_id)
    messages = list(conversation.messages or [])
    if not request.auto:
        messages.append({"role": "user", "content": request.natural_language[:3000], "created_at": datetime.now(timezone.utc).isoformat()})
    conversation.messages = messages[-50:]
    state = {}
    if isinstance(conversation.last_execution, dict):
        state = dict(conversation.last_execution.get("advisor") or {})
        analysis_turns = list(conversation.last_execution.get("operations_analysis") or [])
        if analysis_turns:
            focus = [str(item.get("focus") or item.get("question") or "").strip() for item in analysis_turns[-6:]]
            focus = [item for item in focus if item]
            if focus:
                # Put the operator's latest, explicit plan direction first so
                # the product parser honors it; analysis turns remain attached
                # as context for demand and resource priorities.
                request_message = request.natural_language + "\n经营分析关注方向：" + "；".join(focus)[:1200]
            else:
                request_message = request.natural_language
        else:
            request_message = request.natural_language
    else:
        request_message = request.natural_language
    previous_step = str((conversation.last_execution or {}).get("step") or "")

    advisor = ProductAdvisor(db, hotel_id)
    answer = advisor.respond(request_message, state)
    summary_text = str(answer.get("summary") or "").strip()
    step = str(answer.get("step") or "")
    # OVERVIEW 每轮读的都是同一批经营数据，长总结会和上一轮几乎重复，不再逐轮塞进
    # 对话记录；当前结论由前端根据 advisor.answer 渲染。只有状态变化才写入历史。
    if summary_text and step != "OVERVIEW":
        messages.append({"role": "assistant", "content": summary_text[:2000], "created_at": datetime.now(timezone.utc).isoformat()})
        conversation.messages = messages[-50:]
    plan = dict(answer.get("plan") or {})
    # 记住当前选中的体验，下一轮预算达不到时保持它不变，而不是悄悄换资源。
    primary = answer.get("primary") or {}
    selected_experiences = primary.get("experiences") or []
    if primary:
        # Persist the complete current product, not just its first experience.
        # The next natural-language turn, recommendation badges and candidate
        # generation all read this same state.
        plan["room_type"] = str(primary.get("room_type") or plan.get("room_type") or "")
        plan["target_date"] = str(primary.get("target_date") or plan.get("target_date") or "")
        plan["nights"] = max(1, min(5, int(primary.get("nights") or plan.get("nights") or 1)))
        plan["checkout_date"] = str(primary.get("checkout_date") or plan.get("checkout_date") or "")
        plan["crowd"] = str(primary.get("crowd") or plan.get("crowd") or "")
        plan["party_size"] = int(primary.get("party_size") or plan.get("party_size") or 2)
        plan["resources"] = [str(item.get("name") or "") for item in selected_experiences if item.get("name")]
        plan["resource_schedule"] = [
            {"name": str(item.get("name") or ""), "available_date": str(item.get("available_date") or primary.get("target_date") or "")}
            for item in selected_experiences if item.get("name")
        ]
        plan["public_places"] = [dict(item) for item in (primary.get("public_places") or plan.get("public_places") or []) if isinstance(item, dict) and item.get("slug")]
        plan["selected_resource"] = plan["resources"][0] if plan["resources"] else ""
        plan["services"] = list(primary.get("services") or [])
        plan["price"] = str(primary.get("price") or "")
        plan["visitor_budget"] = primary.get("visitor_budget")
        plan["route_note"] = str(primary.get("route_note") or "")
    saved_analysis = list((conversation.last_execution or {}).get("operations_analysis") or [])
    conversation.last_execution = {
        "advisor": plan,
        "step": step,
        "at": datetime.now(timezone.utc).isoformat(),
        "operations_analysis": saved_analysis[-12:],
        # 刷新页面后仍能恢复当前的经营判断与推荐方案，不必重新跑一轮。
        "answer": answer,
    }
    answer["plan"] = plan

    proposals: list[ProductProposal] = []
    wants_confirm = any(word in request.natural_language for word in ("生成", "确认", "可以", "按这个", "开始生成"))
    # Only a second confirmation generates candidates: the first "我需要生成产品"
    # must show the inventory and the recommendation first.
    ready_to_generate = previous_step in {"PLAN", "READY", "GENERATED"}
    if plan.get("room_type") and plan.get("target_date") and wants_confirm and ready_to_generate:
        room = db.scalar(
            select(RoomInventory)
            .where(
                RoomInventory.hotel_id == hotel_id,
                RoomInventory.room_type == str(plan["room_type"]),
                RoomInventory.available_date == date.fromisoformat(str(plan["target_date"])),
                RoomInventory.status == "AVAILABLE",
            )
            .order_by(RoomInventory.available_count.desc())
        )
        if room is not None:
            theme = "、".join(plan.get("resources") or []) or f"{plan['room_type']}周末组合"
            # plan.crowd 现在存的是代码（COUPLE 等），旧快照里可能是中文标签，两种都要兼容。
            raw_crowd = str(plan.get("crowd") or "")
            crowd_code = CROWD_CODE_BY_LABEL.get(raw_crowd, raw_crowd if raw_crowd.isupper() else "FAMILY")
            selected_resources: list[dict[str, Any]] = []
            selected_names = [str(item) for item in (plan.get("resources") or [])]
            schedule = [item for item in (plan.get("resource_schedule") or []) if isinstance(item, dict) and item.get("name")]
            if schedule:
                for scheduled in schedule:
                    partner = db.scalar(
                        select(PartnerResource)
                        .join(Merchant)
                        .where(
                            Merchant.hotel_id == hotel_id,
                            PartnerResource.available_date == date.fromisoformat(str(scheduled.get("available_date") or plan["target_date"])),
                            PartnerResource.resource_name == str(scheduled["name"]),
                            PartnerResource.status == "AVAILABLE",
                            PartnerResource.package_enabled.is_(True),
                        )
                    )
                    if partner is not None and not any(int(item["resource_id"]) == int(partner.id) for item in selected_resources):
                        selected_resources.append({"resource_type": "PARTNER_RESOURCE", "resource_id": partner.id, "quantity_per_package": int(plan.get("party_size") or 2)})
            elif selected_names:
                partner_rows = list(db.scalars(
                    select(PartnerResource)
                    .join(Merchant)
                    .where(Merchant.hotel_id == hotel_id, PartnerResource.available_date == room.available_date, PartnerResource.resource_name.in_(selected_names), PartnerResource.status == "AVAILABLE")
                ).all())
                for partner in partner_rows:
                    selected_resources.append({"resource_type": "PARTNER_RESOURCE", "resource_id": partner.id, "quantity_per_package": int(plan.get("party_size") or 2)})
            for item in (plan.get("services") or []):
                service_id = int(item.get("id") or 0) if isinstance(item, dict) else 0
                if service_id:
                    selected_resources.append({"resource_type": "HOTEL_SERVICE", "resource_id": service_id, "quantity_per_package": int(item.get("quantity") or plan.get("party_size") or 2)})
            generate_request = GenerateProductRequest(
                target_date=room.available_date,
                nights=max(1, min(5, int(plan.get("nights") or 1))),
                weather="CLOUDY",
                target_crowd=crowd_code,
                party_size=int(plan.get("party_size") or 2),
                minimum_gross_margin=Decimal("0.20"),
                visitor_budget=Decimal(str(plan["visitor_budget"])) if plan.get("visitor_budget") else None,
                preferred_price=Decimal(str(plan["price"])) if plan.get("price") else None,
                theme=theme[:60],
                room_inventory_id=room.id,
                resource_selections=selected_resources,
                variant_count=1,
                creative_direction=(
                    "正式体验：" + "、".join(str(item) for item in (plan.get("resources") or []))
                    + "；酒店权益：" + "、".join(str(item.get("name") if isinstance(item, dict) else item) for item in (plan.get("services") or []))
                    + ("；路线安排：" + str(plan.get("route_note")) if plan.get("route_note") else "")
                )[:800],
            )
            service = ProductProposalService(
                db,
                hotel_id,
                RequestContext(source_channel="WEB_HOTEL", actor_role="HOTEL_OPERATOR", hotel_id=hotel_id, user_id=user.id, conversation_id=str(conversation.id)),
            )
            proposals = service.create_from_request(generate_request, conversation=conversation, natural_language=request.natural_language)
            selected_public_places = [dict(item) for item in (plan.get("public_places") or []) if isinstance(item, dict) and item.get("slug")]
            if selected_public_places:
                for proposal in proposals:
                    product = getattr(proposal, "product", None)
                    if product is None:
                        continue
                    notes = dict(product.experience_notes or {})
                    notes["selected_public_places"] = selected_public_places
                    product.experience_notes = notes
                db.flush()
            answer["step"] = "GENERATED"
            answer["summary"] = f"已按 {plan['room_type']}（{plan['target_date']}）生成 {len(proposals)} 套候选产品。"
            answer["options"] = [
                {"id": "publish", "label": "挑一套发布", "message": "把第一套加入草稿"},
                {"id": "adjust", "label": "继续调整资源", "message": "再换一个合作资源"},
            ]
            answer["question"] = "候选已经生成，可以在下方队列里确认发布；也可以继续告诉我要替换哪个资源。"
    # 生成候选会把 answer.step 改成 GENERATED。会话里同时保存 step 和 answer 快照，
    # 两者都要写成最终值，否则刷新后前端按 step 判断阶段会退回上一阶段。
    execution = dict(conversation.last_execution or {})
    final_step = answer.get("step")
    stored_answer = dict(answer)
    stored_answer["step"] = final_step
    execution["step"] = final_step
    execution["answer"] = stored_answer
    conversation.last_execution = execution
    db.commit()
    db.refresh(conversation)
    return {
        "conversation": conversation,
        "advisor": answer,
        "proposals": [proposal_to_dict(db, item) for item in proposals],
    }


@router.get("/orders/overview", response_model=OrderOverviewResponse)
def orders_overview(db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    """Every order with its category, so the hotel can review sales at a glance."""

    hotel_id = hotel_id_for(db, user)
    intents = list(
        db.scalars(
            select(VisitorIntent)
            .join(TravelProduct)
            .options(selectinload(VisitorIntent.product).selectinload(TravelProduct.resources))
            .where(TravelProduct.hotel_id == hotel_id)
            .order_by(VisitorIntent.created_at.desc())
        ).unique().all()
    )
    confirmed = [item for item in intents if item.reservation_status == "CONFIRMED" and item.product]
    held = [item for item in intents if item.reservation_status == "HELD"]
    cancelled = [item for item in intents if item.reservation_status in {"CANCELLED", "RELEASED"}]

    def amount_for(intent: VisitorIntent) -> tuple[Decimal, bool]:
        snapshot = intent.recommendation_result if isinstance(intent.recommendation_result, dict) else {}
        submitted = snapshot.get("submitted_price")
        if submitted is not None:
            try:
                return Decimal(str(submitted)), False
            except Exception:
                pass
        return Decimal(str(intent.product.suggested_price or 0)), True

    revenue = Decimal("0")
    estimated_amount_count = 0
    for item in confirmed:
        amount, estimated = amount_for(item)
        revenue += amount
        estimated_amount_count += int(estimated)

    crowd_labels = {
        "FAMILY": "亲子家庭", "COUPLE": "两人同行", "FRIENDS": "朋友出行",
        "SOLO": "独自旅行", "LOCAL_WEEKEND": "本地周末", "ALL": "不限客群",
    }
    buckets: dict[str, dict[str, Any]] = {}
    order_rows: list[dict[str, Any]] = []
    today = date.today()
    recent_start = today - timedelta(days=14)
    recent_confirmed: list[VisitorIntent] = []
    recent_order_rows: list[dict[str, Any]] = []
    crowd_counts: dict[str, int] = {}
    product_metrics: dict[int, dict[str, Any]] = {}
    recent_revenue = Decimal("0")
    recent_estimated_count = 0
    for intent in intents:
        product = intent.product
        if product is None:
            continue
        text = f"{product.product_name} {product.theme}"
        category = next(
            (label for label, words in CATEGORY_KEYWORDS.items() if any(word in text for word in words)),
            crowd_labels.get(str(product.target_crowd), "其他"),
        )
        bucket = buckets.setdefault(category, {"label": category, "count": 0, "confirmed": 0, "revenue": Decimal("0")})
        bucket["count"] += 1
        amount, amount_is_estimate = amount_for(intent)
        if intent.reservation_status == "CONFIRMED":
            bucket["confirmed"] += 1
            bucket["revenue"] += amount
        status = {"CONFIRMED": "已成交", "HELD": "预约中", "CANCELLED": "已取消", "RELEASED": "已取消"}.get(str(intent.reservation_status), "已处理")
        order_row = {
            "id": intent.id,
            "product_id": product.id,
            "product_name": product.product_name,
            "category": category,
            "amount": str(amount) if amount is not None else None,
            "amount_is_estimate": amount_is_estimate,
            "target_date": product.target_date.isoformat(),
            "created_at": intent.created_at,
            "confirmed_at": intent.confirmed_at,
            "status": status,
            "product_status": product.status,
            "contact_name": intent.contact_name,
            "contact_phone": intent.contact_phone,
            "note": intent.other_requirements,
        }
        order_rows.append(order_row)

        activity_at = intent.confirmed_at or intent.created_at
        if activity_at is not None and recent_start <= activity_at.date() <= today:
            recent_order_rows.append(order_row)
        if intent.reservation_status == "CONFIRMED" and activity_at is not None and recent_start <= activity_at.date() <= today:
            recent_confirmed.append(intent)
            recent_revenue += amount
            recent_estimated_count += int(amount_is_estimate)
            crowd = str(product.target_crowd or "ALL")
            crowd_counts[crowd] = crowd_counts.get(crowd, 0) + 1
            metric = product_metrics.setdefault(product.id, {"product_id": product.id, "product_name": product.product_name, "confirmed_orders": 0, "revenue": Decimal("0"), "included_experiences": set()})
            metric["confirmed_orders"] += 1
            metric["revenue"] += amount
            metric["included_experiences"].update(
                str(resource.resource_name)
                for resource in (product.resources or [])
                if resource.resource_type == "PARTNER_RESOURCE" and resource.resource_name
            )

    recent_count = len(recent_confirmed)
    recent_crowds = [
        {"target_crowd": crowd, "confirmed_orders": count, "share": round(count * 100 / recent_count, 1)}
        for crowd, count in sorted(crowd_counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    ranked_recent_products = sorted(product_metrics.values(), key=lambda row: (-row["confirmed_orders"], -row["revenue"]))
    recent_products = [
        {
            "product_id": item["product_id"],
            "product_name": item["product_name"],
            "confirmed_orders": item["confirmed_orders"],
            "revenue": str(item["revenue"]),
            "included_experiences": sorted(item["included_experiences"]),
        }
        for item in ranked_recent_products
    ]
    recent_experience_counts: dict[str, int] = {}
    for item in recent_products:
        for experience in item["included_experiences"]:
            recent_experience_counts[experience] = recent_experience_counts.get(experience, 0) + int(item["confirmed_orders"])
    recent_experiences = [
        {"name": name, "confirmed_orders": count}
        for name, count in sorted(recent_experience_counts.items(), key=lambda item: (-item[1], item[0]))
    ]

    return {
        "total": len(intents),
        "confirmed": len(confirmed),
        "held": len(held),
        "cancelled": len(cancelled),
        "confirmed_revenue": str(revenue),
        "sold_product_count": len({item.product_id for item in confirmed}),
        "estimated_amount_count": estimated_amount_count,
        "categories": [
            {"label": bucket["label"], "count": bucket["count"], "confirmed": bucket["confirmed"], "revenue": str(bucket["revenue"])}
            for bucket in sorted(buckets.values(), key=lambda row: row["count"], reverse=True)
        ],
        "recent": {
            "from_date": recent_start.isoformat(),
            "confirmed_count": recent_count,
            "confirmed_revenue": str(recent_revenue),
            "average_order_value": str((recent_revenue / recent_count).quantize(Decimal("0.01"))) if recent_count else None,
            "estimated_amount_count": recent_estimated_count,
            "top_crowds": recent_crowds,
            "top_products": recent_products,
            "top_experiences": recent_experiences,
            "orders": sorted(recent_order_rows, key=lambda row: row["created_at"], reverse=True),
        },
        "orders": order_rows,
    }


@router.post("/ai/conversations/{conversation_id}/analysis")
def analyze_operating_question(conversation_id: int, request: OperationsQueryRequest, db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    """Persist a hotel operator's data question and its factual answer."""
    hotel_id = hotel_id_for(db, user)
    conversation = _hotel_conversation_or_404(db, hotel_id, conversation_id)
    question = request.query.strip()
    normalized_question = question.lower()
    if any(word in normalized_question for word in ("天气", "降雨", "下雨", "雨天")):
        forecasts = WeatherService(db).get_forecast_range("杭州", date.today(), days=15)
        usable = [item for item in forecasts if item.get("usable")]
        rainy = [item for item in usable if str(item.get("scenario") or "").upper() == "RAIN"]
        dates = "、".join(str(item.get("target_date") or "") for item in rainy[:8])
        if usable:
            answer = f"未来15天已取得 {len(usable)} 天有效天气预报，其中 {len(rainy)} 天标记为降雨" + (f"（{dates}）。" if dates else "。")
            answer += "产品组合会据此调整室内外体验排序；天气数据不会单独阻断产品生成。"
        else:
            answer = "未来15天没有可用天气预报，暂时无法判断降雨日期；产品生成仍可继续，并在行程中标注天气待核验。"
        result = {"answer": answer, "focus": answer[:700], "intent": "weather_impact", "facts": {"window_days": 15, "usable_forecast_days": len(usable), "rainy_days": len(rainy)}}
    elif any(word in normalized_question for word in ("知识库", "地点", "景点", "开放时间", "博物馆")):
        places = KnowledgeService(db).search(limit=10)
        names = [str(item.get("name") or "") for item in places if isinstance(item, dict) and item.get("name")]
        answer = "知识库中已有地点：" + ("、".join(names[:8]) if names else "当前没有登记地点") + "."
        answer += "地点可用于非售卖路线建议；目前没有地点与成交订单的结构化关联，无法据此排名历史转化效果。"
        result = {"answer": answer, "focus": answer[:700], "intent": "knowledge_places", "facts": {"place_count": len(places)}}
    else:
        result = OperationsInsightService(db, hotel_id).answer_query(question, window_days=15)
    now = datetime.now(timezone.utc).isoformat()
    messages = list(conversation.messages or [])
    messages.extend([
        {"role": "user", "kind": "OPERATIONS_QUERY", "content": question[:1200], "created_at": now},
        {"role": "assistant", "kind": "OPERATIONS_QUERY", "content": result["answer"], "created_at": now, "facts": result["facts"]},
    ])
    conversation.messages = messages[-50:]
    execution = dict(conversation.last_execution or {})
    prior = list(execution.get("operations_analysis") or [])
    prior.append({"question": question[:1200], "answer": result["answer"], "focus": result["focus"], "intent": result["intent"], "facts": result["facts"]})
    execution["operations_analysis"] = prior[-12:]
    conversation.last_execution = execution
    db.commit()
    db.refresh(conversation)
    return {"conversation": conversation, "answer": result["answer"], "focus": result["focus"], "intent": result["intent"], "facts": result["facts"]}


@router.post("/media/upload")
async def upload_media(file: UploadFile = File(...), user: User = Depends(get_hotel_user)):
    _ = user
    content = await file.read(MAX_MEDIA_BYTES + 1)
    if len(content) > MAX_MEDIA_BYTES:
        raise AppError("MEDIA_CONTENT_INVALID", "图片不能超过 12MB。", field="file")
    return MediaLibraryService().store_upload(content, file.content_type)


@router.post("/media/search")
def search_media(request: MediaSearchRequest, user: User = Depends(get_hotel_user)):
    _ = user
    # prefetch=True: 每张候选图先落到服务器本地，缩略图直接引用本站地址，
    # 既不依赖第三方 CDN，也不会出现「图片显示不出来」。
    return {"items": MediaLibraryService().search_public(request.query, request.limit, prefetch=True)}


@router.post("/media/import")
def import_media(request: MediaImportRequest, user: User = Depends(get_hotel_user)):
    _ = user
    return MediaLibraryService().import_remote(request.url, source=request.source, attribution=request.attribution)


def room_status(count: int, requested: str | None = None) -> str:
    if requested == "DISABLED":
        return "DISABLED"
    if count <= 0:
        return "SOLD_OUT"
    return "LOW_STOCK" if count <= 2 else "AVAILABLE"


def service_status(quantity: int, requested: str | None = None) -> str:
    if requested in {"UNAVAILABLE", "SUSPENDED", "EXPIRED"}:
        return requested
    return "SOLD_OUT" if quantity <= 0 else "AVAILABLE"


def room_snapshot(room: RoomInventory) -> dict:
    return {
        "id": room.id,
        "room_type": room.room_type,
        "available_date": room.available_date.isoformat(),
        "available_count": room.available_count,
        "status": room.status,
        "minimum_price": str(room.minimum_price),
        "normal_price": str(room.normal_price),
        "accounting_cost": str(room.accounting_cost),
        "max_guests": room.max_guests,
        "features": room.features,
        "suitable_crowds": room.suitable_crowds,
        "tags": room.tags,
    }


def service_snapshot(service: HotelService) -> dict:
    return {"id": service.id, "available_quantity": service.available_quantity, "status": service.status, "unit_cost": str(service.unit_cost), "reference_price": str(service.reference_price)}


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    hotel_id = hotel_id_for(db, user)
    # The dashboard is a read path. Releasing expired holds can lock product and
    # resource rows, so leave that reconciliation to order/reservation paths.
    hotel = db.get(Hotel, hotel_id)
    today = date.today()
    target = today + timedelta(days=1)
    room_metrics = db.execute(
        select(
            func.count(RoomInventory.id),
            func.count(RoomInventory.id).filter(RoomInventory.available_date == target),
            func.coalesce(func.sum(RoomInventory.available_count).filter(RoomInventory.available_date == target), 0),
        ).where(RoomInventory.hotel_id == hotel_id)
    ).one()
    resource_metrics = db.execute(
        select(
            func.count(PartnerResource.id),
            func.count(PartnerResource.id).filter(
                PartnerResource.package_enabled.is_(True), PartnerResource.status == "AVAILABLE"
            ),
        )
        .join(Merchant, Merchant.id == PartnerResource.merchant_id)
        .where(Merchant.hotel_id == hotel_id)
    ).one()

    active_statuses = ("ON_SALE", "LOW_STOCK")
    positive_quantity = case((TravelProduct.sale_quantity > 0, TravelProduct.sale_quantity), else_=0)
    product_totals = db.execute(
        select(
            func.count(TravelProduct.id),
            func.count(TravelProduct.id).filter(TravelProduct.status.in_(active_statuses)),
            func.count(TravelProduct.id).filter(TravelProduct.status == "LOW_STOCK"),
            func.coalesce(func.sum(TravelProduct.gross_profit * TravelProduct.sale_quantity).filter(TravelProduct.status.in_(active_statuses)), 0),
            func.coalesce(func.sum(positive_quantity).filter(TravelProduct.status.in_(active_statuses)), 0),
            func.coalesce(func.sum(TravelProduct.suggested_price * positive_quantity).filter(TravelProduct.status.in_(active_statuses)), 0),
        ).where(TravelProduct.hotel_id == hotel_id, TravelProduct.status != "DELETED")
    ).one()

    active_held = (
        (VisitorIntent.reservation_status == "HELD")
        & or_(VisitorIntent.reserved_until.is_(None), VisitorIntent.reserved_until > datetime.now(timezone.utc))
    )
    intent_totals = db.execute(
        select(
            func.count(VisitorIntent.id),
            func.count(VisitorIntent.id).filter(VisitorIntent.reservation_status == "CONFIRMED"),
            func.count(VisitorIntent.id).filter(active_held),
            func.coalesce(func.sum(TravelProduct.suggested_price).filter(VisitorIntent.reservation_status == "CONFIRMED"), 0),
            func.coalesce(func.sum(TravelProduct.gross_profit).filter(VisitorIntent.reservation_status == "CONFIRMED"), 0),
            func.coalesce(func.sum(TravelProduct.suggested_price).filter(active_held), 0),
        )
        .join(TravelProduct, TravelProduct.id == VisitorIntent.product_id)
        .where(TravelProduct.hotel_id == hotel_id)
    ).one()

    # Aggregate facts in SQL so the dashboard and full product list do not each
    # hydrate every TravelProduct and order object into Python.
    product_days = db.execute(
        select(
            TravelProduct.target_date,
            func.count(TravelProduct.id),
            func.coalesce(func.sum(positive_quantity), 0),
            func.coalesce(func.sum(TravelProduct.suggested_price * positive_quantity), 0),
        )
        .where(
            TravelProduct.hotel_id == hotel_id,
            TravelProduct.status.in_(active_statuses),
            TravelProduct.status != "DELETED",
            TravelProduct.target_date.is_not(None),
        )
        .group_by(TravelProduct.target_date)
    ).all()
    confirmed_days = db.execute(
        select(
            # ``func.date`` behaves the same on PostgreSQL and SQLite.  A raw
            # ``cast(..., Date)`` is PostgreSQL-only here: SQLite applies
            # NUMERIC affinity and hands SQLAlchemy an integer, which makes the
            # DateTime result processor raise while building the dashboard.
            func.date(VisitorIntent.confirmed_at),
            func.count(VisitorIntent.id),
            func.coalesce(func.sum(TravelProduct.suggested_price), 0),
            func.coalesce(func.sum(TravelProduct.gross_profit), 0),
        )
        .join(TravelProduct, TravelProduct.id == VisitorIntent.product_id)
        .where(
            TravelProduct.hotel_id == hotel_id,
            VisitorIntent.reservation_status == "CONFIRMED",
            VisitorIntent.confirmed_at.is_not(None),
        )
        .group_by(func.date(VisitorIntent.confirmed_at))
    ).all()

    zero = Decimal("0")
    timeline: dict[date, dict] = {}

    def timeline_point(day: date) -> dict:
        return timeline.setdefault(day, {
            "date": day.isoformat(),
            "confirmed_orders": 0,
            "confirmed_revenue": zero,
            "confirmed_gross_profit": zero,
            "on_sale_products": 0,
            "available_packages": 0,
            "listed_value": zero,
        })

    for offset in range(6, -1, -1):
        timeline_point(today - timedelta(days=offset))
    for product_day, count, packages, value in product_days:
        if isinstance(product_day, str):
            product_day = date.fromisoformat(product_day)
        point = timeline_point(product_day)
        point["on_sale_products"] = int(count or 0)
        point["available_packages"] = int(packages or 0)
        point["listed_value"] = value or zero
    for confirmed_day, count, revenue, gross_profit in confirmed_days:
        if confirmed_day is None:
            continue
        if isinstance(confirmed_day, str):
            confirmed_day = date.fromisoformat(confirmed_day)
        point = timeline_point(confirmed_day)
        point["confirmed_orders"] = int(count or 0)
        point["confirmed_revenue"] = revenue or zero
        point["confirmed_gross_profit"] = gross_profit or zero

    changes = list(db.scalars(
        select(ResourceChangeEvent)
        .where(ResourceChangeEvent.hotel_id == hotel_id)
        .order_by(ResourceChangeEvent.created_at.desc())
        .limit(6)
    ).all())
    return {
        "hotel_id": hotel_id,
        "hotel_name": hotel.name if hotel else "StayScape",
        "target_date": target.isoformat(),
        "room_count": int(room_metrics[0] or 0),
        "expiring_room_count": int(room_metrics[1] or 0),
        "available_room_units": int(room_metrics[2] or 0),
        "partner_resource_count": int(resource_metrics[0] or 0),
        "package_enabled_resource_count": int(resource_metrics[1] or 0),
        "product_count": int(product_totals[0] or 0),
        "on_sale_product_count": int(product_totals[1] or 0),
        "low_stock_product_count": int(product_totals[2] or 0),
        "visitor_intent_count": int(intent_totals[0] or 0),
        "gross_profit_on_sale": product_totals[3] or zero,
        "confirmed_order_count": int(intent_totals[1] or 0),
        "confirmed_revenue": intent_totals[3] or zero,
        "confirmed_gross_profit": intent_totals[4] or zero,
        "held_order_count": int(intent_totals[2] or 0),
        "held_revenue": intent_totals[5] or zero,
        "available_package_count": int(product_totals[4] or 0),
        "listed_value": product_totals[5] or zero,
        "sales_timeline": [timeline[day] for day in sorted(timeline)],
        "recent_changes": [
            {"id": item.id, "event_type": item.event_type, "resource_type": item.resource_type,
             "resource_id": item.resource_id, "reason": item.reason, "processed": item.processed,
             "created_at": item.created_at}
            for item in changes
        ],
    }


@router.get("/rooms", response_model=list[RoomRead])
def rooms(
    db: Session = Depends(get_db),
    user: User = Depends(get_hotel_user),
    target_date: date | None = Query(default=None),
    from_date: date | None = Query(default=None),
    days: int = Query(default=17, ge=1, le=90),
):
    hotel_id = hotel_id_for(db, user)
    if from_date is not None:
        end_date = from_date + timedelta(days=days)
        return list(db.scalars(
            select(RoomInventory)
            .where(
                RoomInventory.hotel_id == hotel_id,
                RoomInventory.available_date >= from_date,
                RoomInventory.available_date < end_date,
            )
            .order_by(RoomInventory.available_date, RoomInventory.room_type, RoomInventory.id)
        ).all())
    items = list_rooms(db, hotel_id)
    return [item for item in items if target_date is None or item.available_date == target_date]


@router.post("/rooms", response_model=RoomRead)
def create_room(request: RoomCreate, db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    if request.minimum_price > request.normal_price:
        raise AppError("VALIDATION_ERROR", "最低售价不能高于正常售价", field="minimum_price")
    hotel_id = hotel_id_for(db, user)
    item = RoomInventory(hotel_id=hotel_id, **request.model_dump(), status=room_status(request.available_count))
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.patch("/rooms/{room_id}", response_model=RoomRead)
async def update_room(room_id: int, request: RoomUpdate, db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    hotel_id = hotel_id_for(db, user)
    room = db.scalar(select(RoomInventory).where(RoomInventory.id == room_id, RoomInventory.hotel_id == hotel_id).with_for_update())
    if not room:
        raise AppError("NOT_FOUND", "客房库存不存在", status_code=404)
    old = room_snapshot(room)
    data = request.model_dump(exclude_unset=True, exclude={"reason"})
    for key, value in data.items():
        setattr(room, key, value)
    if room.minimum_price > room.normal_price:
        raise AppError("VALIDATION_ERROR", "最低售价不能高于正常售价", field="minimum_price")
    if room.available_count < 0 or room.accounting_cost <= 0:
        raise AppError("VALIDATION_ERROR", "库存和核算成本必须合法")
    room.status = room_status(room.available_count, request.status or room.status)
    event = ResourceChangeEvent(event_type="ROOM_INVENTORY_CHANGED", resource_type="ROOM", resource_id=room.id, hotel_id=hotel_id, old_value=old, new_value=room_snapshot(room), reason=request.reason, operator_role=user.role, operator_id=user.id)
    db.add(event)
    db.flush()
    affected = ProductService(db, hotel_id).recalculate_for_event(event)
    db.commit()
    await manager.broadcast(hotel_id, {"type": "RESOURCE_CHANGE", "title": "临期客房发生变化", "message": request.reason, "affectedProducts": affected})
    db.refresh(room)
    return room


@router.get("/services", response_model=list[ServiceRead])
def services(db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    return list_services(db, hotel_id_for(db, user))


@router.post("/services", response_model=ServiceRead)
def create_service(request: ServiceCreate, db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    if request.start_time and request.end_time and request.start_time >= request.end_time:
        raise AppError("TIME_INVALID", "服务开始时间必须早于结束时间")
    hotel_id = hotel_id_for(db, user)
    item = HotelService(hotel_id=hotel_id, **request.model_dump(), status=service_status(request.available_quantity))
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.patch("/services/{service_id}", response_model=ServiceRead)
async def update_service(service_id: int, request: ServiceUpdate, db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    hotel_id = hotel_id_for(db, user)
    service = db.scalar(select(HotelService).where(HotelService.id == service_id, HotelService.hotel_id == hotel_id).with_for_update())
    if not service:
        raise AppError("NOT_FOUND", "酒店服务不存在", status_code=404)
    old = service_snapshot(service)
    data = request.model_dump(exclude_unset=True, exclude={"reason"})
    for key, value in data.items():
        setattr(service, key, value)
    if service.available_quantity < 0:
        raise AppError("VALIDATION_ERROR", "服务名额不能为负数", field="available_quantity")
    if service.start_time and service.end_time and service.start_time >= service.end_time:
        raise AppError("TIME_INVALID", "服务开始时间必须早于结束时间")
    service.status = service_status(service.available_quantity, service.status)
    event_type = "HOTEL_SERVICE_STATUS_CHANGED" if old["status"] != service.status else "HOTEL_SERVICE_QUANTITY_CHANGED"
    event = ResourceChangeEvent(event_type=event_type, resource_type="HOTEL_SERVICE", resource_id=service.id, hotel_id=hotel_id, old_value=old, new_value=service_snapshot(service), reason=request.reason, operator_role=user.role, operator_id=user.id)
    db.add(event)
    db.flush()
    affected = ProductService(db, hotel_id).recalculate_for_event(event)
    db.commit()
    await manager.broadcast(hotel_id, {"type": "RESOURCE_CHANGE", "title": "酒店服务发生变化", "message": request.reason, "affectedProducts": affected})
    db.refresh(service)
    return service


@router.get("/merchants", response_model=list[MerchantRead])
def merchants(db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    return list(db.scalars(select(Merchant).where(Merchant.hotel_id == hotel_id_for(db, user)).order_by(Merchant.id)).all())


@router.get("/resources", response_model=list[PartnerResourceRead])
def resources(db: Session = Depends(get_db), user: User = Depends(get_hotel_user), only_package_enabled: bool | None = None):
    hotel_id = hotel_id_for(db, user)
    items = list_partner_resources(db, hotel_id)
    result = []
    for item in items:
        if only_package_enabled is not None and item.package_enabled != only_package_enabled:
            continue
        count = db.scalar(select(func.count(ProductResource.id)).where(ProductResource.resource_type == "PARTNER_RESOURCE", ProductResource.resource_id == item.id)) or 0
        result.append(partner_resource_to_dict(item, int(count)))
    return result


@router.post("/resources", response_model=PartnerResourceRead)
async def create_partner_resource(request: HotelPartnerResourceCreate, db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    hotel_id = hotel_id_for(db, user)
    if request.available_date < date.today():
        raise AppError("DATE_INVALID", "合作资源可用日期不能早于今天", field="available_date")
    merchant = db.scalar(select(Merchant).where(Merchant.id == request.merchant_id, Merchant.hotel_id == hotel_id))
    if merchant is None:
        raise AppError("MERCHANT_NOT_FOUND", "请选择当前酒店名下的合作商户", field="merchant_id", status_code=404)
    if request.start_time and request.end_time and request.start_time >= request.end_time:
        raise AppError("TIME_INVALID", "活动开始时间必须早于结束时间")
    data = request.model_dump(exclude={"merchant_id"})
    resource = PartnerResource(
        merchant_id=merchant.id,
        **data,
        status="AVAILABLE" if request.remaining_capacity > 0 else "SOLD_OUT",
    )
    db.add(resource)
    db.flush()
    event = ResourceChangeEvent(
        event_type="PARTNER_RESOURCE_ADDED",
        resource_type="PARTNER_RESOURCE",
        resource_id=resource.id,
        hotel_id=hotel_id,
        old_value={},
        new_value={
            "resource_name": resource.resource_name,
            "available_date": resource.available_date.isoformat(),
            "remaining_capacity": resource.remaining_capacity,
            "package_enabled": resource.package_enabled,
        },
        reason="酒店在合作资源池新增资源",
        operator_role=user.role,
        operator_id=user.id,
        processed=True,
    )
    db.add(event)
    db.commit()
    await manager.broadcast(hotel_id, {"type": "RESOURCE_CHANGE", "title": "新增合作资源", "message": f"{resource.resource_name}已加入合作资源池", "affectedProducts": []})
    db.refresh(resource)
    return partner_resource_to_dict(resource, 0)


@router.patch("/resources/{resource_id}", response_model=PartnerResourceRead)
async def update_partner_resource(resource_id: int, request: PartnerResourceUpdate, db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    hotel_id = hotel_id_for(db, user)
    resource = db.scalar(select(PartnerResource).join(Merchant).options(selectinload(PartnerResource.merchant)).where(PartnerResource.id == resource_id, Merchant.hotel_id == hotel_id).with_for_update())
    if resource is None:
        raise AppError("NOT_FOUND", "合作资源不存在", status_code=404)
    values = request.model_dump(exclude_unset=True, exclude={"reason"})
    merchant_id = values.pop("merchant_id", None)
    if merchant_id is not None:
        merchant = db.scalar(select(Merchant).where(Merchant.id == merchant_id, Merchant.hotel_id == hotel_id))
        if merchant is None:
            raise AppError("MERCHANT_NOT_FOUND", "请选择当前酒店名下的合作商户", field="merchant_id", status_code=404)
        resource.merchant_id = merchant.id
    if values.get("available_date") and values["available_date"] < date.today():
        raise AppError("DATE_INVALID", "合作资源可用日期不能早于今天", field="available_date")
    start_time = values.get("start_time", resource.start_time)
    end_time = values.get("end_time", resource.end_time)
    if start_time and end_time and start_time >= end_time:
        raise AppError("TIME_INVALID", "活动开始时间必须早于结束时间")
    old = {key: (str(getattr(resource, key)) if getattr(resource, key) is not None else None) for key in values}
    for key, value in values.items():
        setattr(resource, key, value)
    new = request.model_dump(exclude_unset=True, exclude={"reason"}, mode="json")
    event = ResourceChangeEvent(event_type="PARTNER_RESOURCE_UPDATED", resource_type="PARTNER_RESOURCE", resource_id=resource.id, hotel_id=hotel_id, old_value=old, new_value=new, reason=request.reason, operator_role=user.role, operator_id=user.id)
    db.add(event)
    db.flush()
    affected = ProductService(db, hotel_id).recalculate_for_event(event)
    db.commit()
    await manager.broadcast(hotel_id, {"type": "RESOURCE_CHANGE", "title": "合作资源已更新", "message": resource.resource_name, "affectedProducts": affected})
    db.refresh(resource)
    count = db.scalar(select(func.count(ProductResource.id)).where(ProductResource.resource_type == "PARTNER_RESOURCE", ProductResource.resource_id == resource.id)) or 0
    return partner_resource_to_dict(resource, int(count))


@router.patch("/resources/{resource_id}/package", response_model=PartnerResourceRead)
async def toggle_package(
    resource_id: int,
    request: PackageToggleRequest | None = Body(default=None),
    package_enabled: bool | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_hotel_user),
):
    enabled = request.package_enabled if request is not None else package_enabled
    if enabled is None:
        raise AppError("VALIDATION_ERROR", "请提供组包许可状态", field="package_enabled")
    hotel_id = hotel_id_for(db, user)
    resource = db.scalar(select(PartnerResource).join(Merchant).options(selectinload(PartnerResource.merchant)).where(PartnerResource.id == resource_id, Merchant.hotel_id == hotel_id).with_for_update())
    if not resource:
        raise AppError("NOT_FOUND", "合作资源不存在", status_code=404)
    old = {"package_enabled": resource.package_enabled, "status": resource.status}
    resource.package_enabled = enabled
    event = ResourceChangeEvent(event_type="PARTNER_RESOURCE_STATUS_CHANGED", resource_type="PARTNER_RESOURCE", resource_id=resource.id, hotel_id=hotel_id, old_value=old, new_value={"package_enabled": resource.package_enabled, "status": resource.status}, reason="酒店调整组包许可", operator_role=user.role, operator_id=user.id)
    db.add(event)
    db.flush()
    affected = ProductService(db, hotel_id).recalculate_for_event(event)
    db.commit()
    await manager.broadcast(hotel_id, {"type": "RESOURCE_CHANGE", "title": "合作资源组包许可发生变化", "message": "酒店调整了资源组包许可", "affectedProducts": affected})
    db.refresh(resource)
    count = db.scalar(select(func.count(ProductResource.id)).where(ProductResource.resource_type == "PARTNER_RESOURCE", ProductResource.resource_id == resource.id)) or 0
    return partner_resource_to_dict(resource, int(count))


@router.patch("/resources/{resource_id}/media", response_model=PartnerResourceRead)
async def update_resource_media(resource_id: int, request: ResourceMediaUpdate, db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    hotel_id = hotel_id_for(db, user)
    resource = db.scalar(select(PartnerResource).join(Merchant).options(selectinload(PartnerResource.merchant)).where(PartnerResource.id == resource_id, Merchant.hotel_id == hotel_id).with_for_update())
    if not resource:
        raise AppError("NOT_FOUND", "合作资源不存在", status_code=404)
    resource.image_url = request.image_url
    resource.image_source = request.image_source
    resource.image_attribution = request.image_attribution
    event = ResourceChangeEvent(event_type="PARTNER_RESOURCE_MEDIA_CHANGED", resource_type="PARTNER_RESOURCE", resource_id=resource.id, hotel_id=hotel_id, old_value={}, new_value={"image_url": bool(resource.image_url)}, reason="酒店更新合作资源图片", operator_role=user.role, operator_id=user.id, processed=True)
    db.add(event)
    db.commit()
    await manager.broadcast(hotel_id, {"type": "RESOURCE_CHANGE", "title": "合作资源图片已更新", "message": resource.resource_name, "affectedProducts": []})
    db.refresh(resource)
    count = db.scalar(select(func.count(ProductResource.id)).where(ProductResource.resource_type == "PARTNER_RESOURCE", ProductResource.resource_id == resource.id)) or 0
    return partner_resource_to_dict(resource, int(count))


@router.patch("/resources/{resource_id}/address", response_model=PartnerResourceRead)
async def update_resource_address(resource_id: int, request: ResourceAddressUpdate, db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    hotel_id = hotel_id_for(db, user)
    resource = db.scalar(select(PartnerResource).join(Merchant).options(selectinload(PartnerResource.merchant)).where(PartnerResource.id == resource_id, Merchant.hotel_id == hotel_id).with_for_update())
    if not resource:
        raise AppError("NOT_FOUND", "合作资源不存在", status_code=404)
    old_address = resource.address or ""
    resource.address = request.address.strip()
    event = ResourceChangeEvent(event_type="PARTNER_RESOURCE_ADDRESS_CHANGED", resource_type="PARTNER_RESOURCE", resource_id=resource.id, hotel_id=hotel_id, old_value={"address": old_address}, new_value={"address": resource.address}, reason="酒店补充合作资源详细地址", operator_role=user.role, operator_id=user.id, processed=True)
    db.add(event)
    db.commit()
    await manager.broadcast(hotel_id, {"type": "RESOURCE_CHANGE", "title": "合作资源地点已更新", "message": resource.resource_name, "affectedProducts": []})
    db.refresh(resource)
    count = db.scalar(select(func.count(ProductResource.id)).where(ProductResource.resource_type == "PARTNER_RESOURCE", ProductResource.resource_id == resource.id)) or 0
    return partner_resource_to_dict(resource, int(count))


@router.get("/products", response_model=ProductListResponse)
def products(
    db: Session = Depends(get_db),
    user: User = Depends(get_hotel_user),
    status: str | None = None,
    limit: int | None = Query(default=None, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    target_date: date | None = None,
    include_marketing_assets: bool = True,
):
    hotel_id = hotel_id_for(db, user)
    excluded_status = None if status else "PENDING_CONFIRMATION"
    if include_marketing_assets:
        items = list_products(
            db,
            hotel_id,
            limit=limit,
            offset=offset,
            status=status,
            exclude_status=excluded_status,
            target_date=target_date,
        )
    else:
        items = list_products_for_serialization(
            db,
            hotel_id,
            limit=limit,
            offset=offset,
            status=status,
            exclude_status=excluded_status,
            target_date=target_date,
        )

    count_query = select(func.count(TravelProduct.id)).where(
        TravelProduct.hotel_id == hotel_id,
        TravelProduct.status != "DELETED",
    )
    dates_query = select(
        TravelProduct.target_date,
        func.coalesce(func.sum(TravelProduct.sale_quantity), 0),
    ).where(
        TravelProduct.hotel_id == hotel_id,
        TravelProduct.status != "DELETED",
    )
    if status:
        count_query = count_query.where(TravelProduct.status == status)
        dates_query = dates_query.where(TravelProduct.status == status)
    else:
        count_query = count_query.where(TravelProduct.status != "PENDING_CONFIRMATION")
        dates_query = dates_query.where(TravelProduct.status != "PENDING_CONFIRMATION")
    if target_date is not None:
        count_query = count_query.where(TravelProduct.target_date == target_date)
    total = int(db.scalar(count_query) or 0)
    dates = []
    if offset == 0:
        dates = [
            {"target_date": day, "sale_quantity": int(quantity or 0)}
            for day, quantity in db.execute(
                dates_query.group_by(TravelProduct.target_date).order_by(TravelProduct.target_date)
            )
        ]
    resource_cache = _product_resource_cache(db, hotel_id, items)
    return {
        "items": [
            product_to_dict(
                item,
                resource_cache=resource_cache,
                include_marketing_assets=include_marketing_assets,
            )
            for item in items
        ],
        "total": total,
        "dates": dates,
    }


@router.post("/products/generate", response_model=ProductGenerateResponse)
def generate_product(request: GenerateProductRequest, db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    generated = ProductService(db, hotel_id_for(db, user)).generate_many(request)
    db.commit()
    products = [item[0] for item in generated]
    trace_ids = [item[2] for item in generated]
    log = db.scalar(select(SkillCallLog).where(SkillCallLog.trace_id == trace_ids[0])) if trace_ids else None
    return {
        "product": product_to_dict(products[0]),
        "products": [product_to_dict(item) for item in products],
        "trace_id": generated[0][2],
        "trace_ids": trace_ids,
        "validation": generated[0][1],
        "fallback_used": any(item[3] for item in generated),
        "provider": log.provider if log else "MOCK",
        "transport": log.transport if log else "mock",
        "agent_id": log.agent_id if log else "",
        "skill_name": log.skill_name if log else "stayscape-product-generator",
        "skill_version": log.skill_version if log else "",
    }


@router.post("/products/interpret", response_model=ProductDraftInterpretResponse)
def interpret_product_request(request: ProductDraftInterpretRequest, user: User = Depends(get_hotel_user)):
    # Authentication keeps the operator's free-text brief within their own
    # workspace.  This parser has no model call and never writes inventory.
    _ = user
    return interpret_product_draft(request.natural_language)


@router.get("/products/{product_id}", response_model=ProductDetailResponse)
def product_detail(product_id: int, db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    product = get_product(db, product_id)
    if not product or product.hotel_id != hotel_id_for(db, user):
        raise AppError("NOT_FOUND", "产品不存在", status_code=404)
    data = visitor_product_to_dict(product)
    # Draft preview and public detail share the same visitor-facing sections.
    from .visitor import build_detail_sections
    data["detail_sections"] = build_detail_sections(db, product, data)
    return {**data, "adjustments": product_to_dict(product, include_adjustments=True).get("adjustments", [])}


@router.patch("/products/{product_id}", response_model=ProductRead)
def update_product(product_id: int, request: ProductUpdateRequest, db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    hotel_id = hotel_id_for(db, user)
    product = get_product(db, product_id)
    if not product or product.hotel_id != hotel_id or product.status == "DELETED":
        raise AppError("NOT_FOUND", "产品不存在", status_code=404)

    target_date = request.target_date or product.target_date
    room_id = request.room_inventory_id or product.room_inventory_id
    room = db.scalar(select(RoomInventory).where(RoomInventory.id == room_id, RoomInventory.hotel_id == hotel_id))
    if not room:
        raise AppError("NOT_FOUND", "产品关联客房不存在", status_code=404)
    if room.available_date != target_date:
        same_type = db.scalar(select(RoomInventory).where(RoomInventory.hotel_id == hotel_id, RoomInventory.room_type == room.room_type, RoomInventory.available_date == target_date).order_by(RoomInventory.available_count.desc()))
        if same_type:
            room = same_type
            room_id = same_type.id
        else:
            raise AppError("DATE_NOT_MATCHED", "没有找到目标日期可用的同房型库存，请先维护客房日期", field="target_date", retryable=True)

    if target_date != product.target_date or room_id != product.room_inventory_id:
        for row in product.resources:
            if row.resource_type == "HOTEL_SERVICE":
                source = db.get(HotelService, row.resource_id)
            elif row.resource_type == "PARTNER_RESOURCE":
                source = db.get(PartnerResource, row.resource_id)
            else:
                source = room
            if source is not None and source.available_date != target_date:
                raise AppError("DATE_NOT_MATCHED", f"资源{row.resource_name}未维护目标日期，请先调整资源日期", field="target_date", retryable=True)

    changed = request.model_dump(exclude_unset=True, exclude={"regenerate_marketing", "target_date", "room_inventory_id", "marketing_assets", "visitor_copy"})
    if request.target_date is not None:
        changed["target_date"] = target_date
    if request.room_inventory_id is not None or target_date != product.target_date:
        changed["room_inventory_id"] = room_id
    if target_date != product.target_date:
        forecast = WeatherService(db).get_forecast("杭州", target_date)
        if forecast.get("usable"):
            changed["weather"] = str(forecast.get("scenario") or product.weather)
        else:
            note = "出发日前一天更新天气预报。"
            changed["risk_message"] = f"{product.risk_message} {note}".strip()
    weather_or_context_changed = any(key in changed for key in ("target_date", "room_inventory_id", "weather", "target_crowd"))
    for key, value in changed.items():
        setattr(product, key, value)
    if request.marketing_assets is not None:
        # 摄影/文案素材按 asset_type 合并，运营可以逐条改标题、正文、视觉方向
        # 与行动号召，不必整包重新生成。
        incoming = {
            str(asset.get("asset_type")): dict(asset)
            for asset in request.marketing_assets
            if isinstance(asset, dict) and asset.get("asset_type")
        }
        merged: list[Any] = []
        for asset in product.marketing_assets or []:
            if isinstance(asset, dict) and str(asset.get("asset_type")) in incoming:
                merged.append({**asset, **incoming.pop(str(asset.get("asset_type")))})
            else:
                merged.append(asset)
        merged.extend(incoming.values())
        product.marketing_assets = merged
    if request.visitor_copy is not None:
        notes = dict(product.experience_notes or {})
        previous_copy = dict(notes.get("visitor_copy") or {})
        incoming_copy = dict(request.visitor_copy)
        if isinstance(incoming_copy.get("resource_descriptions"), dict):
            previous_copy["resource_descriptions"] = {
                **dict(previous_copy.get("resource_descriptions") or {}),
                **incoming_copy.pop("resource_descriptions"),
            }
        if isinstance(incoming_copy.get("resource_names"), dict):
            previous_copy["resource_names"] = {
                **dict(previous_copy.get("resource_names") or {}),
                **incoming_copy.pop("resource_names"),
            }
        if isinstance(incoming_copy.get("itinerary"), list):
            previous_copy["itinerary"] = incoming_copy.pop("itinerary")
        previous_copy.update(incoming_copy)
        notes["visitor_copy"] = previous_copy
        product.experience_notes = notes
    db.flush()

    service = ProductService(db, hotel_id)
    if weather_or_context_changed:
        service.recalculate_product(product)
        reconcile_published_capacity(db, hotel_id, priority_product_id=product.id if product.status in {"ON_SALE", "LOW_STOCK"} else None)
    if request.regenerate_marketing or any(key in changed for key in ("theme", "weather", "target_crowd")):
        service.regenerate_marketing(product)
    db.commit()
    return visitor_product_to_dict(product)


@router.post("/products/{product_id}/copy-rewrite")
def rewrite_product_copy(product_id: int, request: CopyRewriteRequest, db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    hotel_id = hotel_id_for(db, user)
    product = get_product(db, product_id)
    if not product or product.hotel_id != hotel_id or product.status == "DELETED":
        raise AppError("NOT_FOUND", "产品不存在", status_code=404)
    field_labels = {
        "product_name": "产品名称", "marketing_title": "游客端标题", "marketing_content": "产品介绍",
        "recommendation_reason": "推荐理由", "risk_message": "出行提示", "resource_title": "体验名称",
        "resource_description": "体验介绍", "itinerary_title": "行程标题", "itinerary_description": "行程说明",
        "itinerary_summary": "当日行程概述", "marketing_asset_title": "营销素材标题", "marketing_asset_content": "营销素材正文",
        "detail_text": "游客端详情文案",
    }
    direction = (
        f"只重写{field_labels[request.field]}，现有文案：{request.current_text}。"
        f"上下文：{request.context}。只返回适合直接展示给游客的一段中文，不改变日期、地址、价格、包含权益和承诺，不写‘以实际情况为准’等空泛提示。"
    )
    service = ProductService(db, hotel_id)
    payload = service._marketing_payload(product, creative_direction=direction, style="SEEDING")
    result = service.orchestrator.generate_marketing(payload)
    output = result.value
    title_fields = {"product_name", "marketing_title", "resource_title", "itinerary_title", "marketing_asset_title"}
    replacement = output.marketing_title if request.field in title_fields else output.marketing_content
    replacement = str(replacement or "").strip()
    if not replacement:
        raise AppError("COPY_REWRITE_EMPTY", "本次没有生成可用文案，请重试", retryable=True)
    return {"replacement_text": replacement, "field": request.field, "trace_id": result.trace_id, "fallback_used": result.fallback_used}


@router.post("/products/{product_id}/batch-apply")
def batch_apply_product(product_id: int, request: ProductBatchApplyRequest, db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    hotel_id = hotel_id_for(db, user)
    source = get_product(db, product_id)
    if not source or source.hotel_id != hotel_id or source.status == "DELETED":
        raise AppError("NOT_FOUND", "产品不存在", status_code=404)
    source_resources = [row for row in source.resources if row.resource_type != "ROOM"]
    if not source_resources:
        raise AppError("PRODUCT_RESOURCES_MISSING", "产品没有可复制的体验或酒店权益", status_code=409)
    created: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    seen: set[tuple[date, int]] = set()

    def date_copy(text: str, target: date) -> str:
        old = source.target_date
        result = str(text or "").replace(old.isoformat(), target.isoformat())
        result = result.replace(f"{old.month}月{old.day}日", f"{target.month}月{target.day}日")
        return result

    for target in request.targets:
        key = (target.target_date, target.room_inventory_id)
        if key in seen:
            skipped.append({"target_date": target.target_date.isoformat(), "room_inventory_id": target.room_inventory_id, "reason": "目标日期与房型重复"})
            continue
        seen.add(key)
        room = db.scalar(select(RoomInventory).where(RoomInventory.id == target.room_inventory_id, RoomInventory.hotel_id == hotel_id))
        if not room or room.available_date != target.target_date:
            skipped.append({"target_date": target.target_date.isoformat(), "room_inventory_id": target.room_inventory_id, "reason": "房型与目标日期不匹配"})
            continue
        if room.status != "AVAILABLE" or room.available_count <= 0 or room.max_guests < source.party_size:
            skipped.append({"target_date": target.target_date.isoformat(), "room_inventory_id": target.room_inventory_id, "room_type": room.room_type, "reason": "房间已售罄、停用或接待人数不足"})
            continue

        mapped: list[tuple[ProductResource, HotelService | PartnerResource]] = []
        reason = ""
        for row in source_resources:
            if row.resource_type == "HOTEL_SERVICE":
                resource = db.scalar(select(HotelService).where(
                    HotelService.hotel_id == hotel_id,
                    HotelService.available_date == target.target_date,
                    HotelService.service_name == row.resource_name,
                    HotelService.status == "AVAILABLE",
                    HotelService.available_quantity >= row.quantity_per_package,
                ).order_by(HotelService.id))
                if resource is None:
                    reason = f"{row.resource_name}在目标日期没有足够可用名额"
                    break
            elif row.resource_type == "PARTNER_RESOURCE":
                resource = db.scalar(select(PartnerResource).join(Merchant).options(selectinload(PartnerResource.merchant)).where(
                    Merchant.hotel_id == hotel_id,
                    PartnerResource.available_date == target.target_date,
                    PartnerResource.resource_name == row.resource_name,
                    PartnerResource.package_enabled.is_(True),
                    PartnerResource.status == "AVAILABLE",
                    PartnerResource.remaining_capacity >= row.quantity_per_package,
                    Merchant.cooperation_status == "ACTIVE",
                ).order_by(PartnerResource.id))
                if resource is None:
                    reason = f"{row.resource_name}在目标日期没有可组包名额"
                    break
            else:
                continue
            mapped.append((row, resource))
        if reason:
            skipped.append({"target_date": target.target_date.isoformat(), "room_type": room.room_type, "reason": reason})
            continue

        early = any(isinstance(resource, PartnerResource) and resource.start_time is not None and resource.start_time.hour < 15 for _, resource in mapped)
        has_baggage = any(isinstance(resource, HotelService) and (resource.service_type == "LUGGAGE_STORAGE" or "行李寄存" in resource.service_name) for _, resource in mapped)
        if early and not has_baggage:
            baggage = db.scalar(select(HotelService).where(
                HotelService.hotel_id == hotel_id,
                HotelService.available_date == target.target_date,
                HotelService.status == "AVAILABLE",
                HotelService.available_quantity > 0,
                or_(HotelService.service_type == "LUGGAGE_STORAGE", HotelService.service_name.contains("行李寄存")),
            ).order_by(HotelService.id))
            if baggage is None:
                skipped.append({"target_date": target.target_date.isoformat(), "room_type": room.room_type, "reason": "首项体验早于入住时间，目标日期没有行李寄存服务"})
                continue
            extra_row = ProductResource(resource_type="HOTEL_SERVICE", resource_id=baggage.id, resource_name=baggage.service_name, quantity_per_package=1, unit_cost=baggage.unit_cost, replaceable=baggage.replaceable, required=True)
            mapped.append((extra_row, baggage))

        selection_request = GenerateProductRequest(
            target_date=target.target_date,
            weather=source.weather,
            target_crowd=source.target_crowd,
            party_size=source.party_size,
            nights=source.nights,
            minimum_gross_margin=source.minimum_gross_margin_requirement,
            visitor_budget=source.visitor_budget_limit,
            theme=source.theme,
            room_inventory_id=room.id,
            preferred_price=source.price_anchor,
            resource_selections=[{"resource_type": row.resource_type, "resource_id": resource.id, "quantity_per_package": row.quantity_per_package} for row, resource in mapped],
        )
        engine = ProductService(db, hotel_id)
        try:
            for _, resource in mapped:
                if isinstance(resource, HotelService):
                    engine._validate_service(resource, selection_request, next(row.quantity_per_package for row, candidate in mapped if candidate.id == resource.id))
                else:
                    engine._validate_partner(resource, selection_request, next(row.quantity_per_package for row, candidate in mapped if candidate.id == resource.id))
            with db.begin_nested():
                old_room_name = str(getattr(getattr(source, "room_inventory", None), "room_type", "") or "")
                title = date_copy(source.product_name, target.target_date).replace(old_room_name, room.room_type) if old_room_name else date_copy(source.product_name, target.target_date)
                cloned_resources = [ProductResource(
                    resource_type="ROOM", resource_id=room.id, resource_name=room.room_type,
                    quantity_per_package=1, unit_cost=room.accounting_cost, replaceable=False, required=True,
                )]
                for source_row, resource in mapped:
                    cloned_resources.append(ProductResource(
                        resource_type=source_row.resource_type,
                        resource_id=resource.id,
                        resource_name=resource.service_name if isinstance(resource, HotelService) else resource.resource_name,
                        quantity_per_package=source_row.quantity_per_package,
                        unit_cost=resource.unit_cost if isinstance(resource, HotelService) else resource.settlement_price,
                        replaceable=resource.replaceable if isinstance(resource, HotelService) else True,
                        required=True,
                    ))
                clone = TravelProduct(
                    hotel_id=hotel_id,
                    product_code=f"SS-{target.target_date:%Y%m%d}-{uuid4().hex[:8].upper()}",
                    product_name=title,
                    theme=source.theme,
                    target_crowd=source.target_crowd,
                    party_size=source.party_size,
                    nights=source.nights,
                    weather=source.weather,
                    target_date=target.target_date,
                    room_inventory_id=room.id,
                    listed_quantity=min(int(source.listed_quantity or 0), int(room.available_count or 0)),
                    sale_quantity=min(int(source.sale_quantity or 0), int(room.available_count or 0)),
                    unit_cost=source.unit_cost,
                    minimum_allowed_price=source.minimum_allowed_price,
                    suggested_price=source.suggested_price,
                    gross_profit=source.gross_profit,
                    gross_margin=source.gross_margin,
                    minimum_gross_margin_requirement=source.minimum_gross_margin_requirement,
                    visitor_budget_limit=source.visitor_budget_limit,
                    price_anchor=source.price_anchor,
                    bottleneck_resource=source.bottleneck_resource,
                    marketing_title=date_copy(source.marketing_title, target.target_date),
                    marketing_content=date_copy(source.marketing_content, target.target_date),
                    marketing_assets=source.marketing_assets or [],
                    recommendation_reason=date_copy(source.recommendation_reason, target.target_date),
                    risk_message=source.risk_message,
                    experience_notes=dict(source.experience_notes or {}),
                    status="DRAFT",
                    resources=cloned_resources,
                )
                db.add(clone)
                db.flush()
                engine.recalculate_product(clone)
                if clone.sale_quantity <= 0 or clone.status in {"PAUSED", "SOLD_OUT"}:
                    raise AppError("TARGET_CAPACITY_INSUFFICIENT", "目标日期的客房或体验容量不足，未创建产品")
                clone.status = "DRAFT"
                db.flush()
                created.append({"id": clone.id, "product_name": clone.product_name, "target_date": clone.target_date.isoformat(), "room_type": room.room_type, "sale_quantity": clone.sale_quantity})
        except AppError as exc:
            skipped.append({"target_date": target.target_date.isoformat(), "room_type": room.room_type, "reason": exc.message})
    db.commit()
    return {"created": created, "skipped": skipped, "created_count": len(created), "skipped_count": len(skipped)}


@router.post("/products/{product_id}/refine", response_model=ProductRefineResponse)
def refine_product_conversationally(
    product_id: int,
    request: ProductRefineRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_hotel_user),
):
    """One natural-language edit on one product.

    The Skill decides which layer the sentence belongs to (content / experience
    / equity), applies only the fields the operator named, and every equity
    change is recalculated against real capacity, cost, margin and weather.
    """

    hotel_id = hotel_id_for(db, user)
    product = get_product(db, product_id)
    if not product or product.hotel_id != hotel_id or product.status == "DELETED":
        raise AppError("NOT_FOUND", "产品不存在", status_code=404)
    result = ProductRefiner(db, hotel_id).refine(product, request.natural_language)
    db.commit()
    db.refresh(product)
    return {**result, "product": visitor_product_to_dict(product, nights=max(1, int(product.nights or 1)))}


@router.get("/products/{product_id}/refinements")
def product_refinements(product_id: int, db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    """这个商品的自然语言修改历史（每一条 = 一个版本）。"""

    hotel_id = hotel_id_for(db, user)
    product = get_product(db, product_id)
    if not product or product.hotel_id != hotel_id:
        raise AppError("NOT_FOUND", "产品不存在", status_code=404)
    return {"version": int(getattr(product, "version", 1) or 1), "items": ProductRefiner(db, hotel_id).history(product)}


@router.post("/products/{product_id}/refinements/{refinement_id}/rollback")
def rollback_product_refinement(product_id: int, refinement_id: int, db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    """回退到某一次微调之前，并把回退本身也记成一条新版本。"""

    hotel_id = hotel_id_for(db, user)
    product = get_product(db, product_id)
    if not product or product.hotel_id != hotel_id:
        raise AppError("NOT_FOUND", "产品不存在", status_code=404)
    result = ProductRefiner(db, hotel_id).rollback(product, refinement_id)
    db.commit()
    db.refresh(product)
    return {**result, "product": product_to_dict(product)}


@router.post("/products/{product_id}/publish-check")
def product_publish_check(product_id: int, db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    """发布前再读一次最新库存与合作名额，返回能不能发、最多能发几套和替代资源。"""

    hotel_id = hotel_id_for(db, user)
    product = get_product(db, product_id)
    if not product or product.hotel_id != hotel_id:
        raise AppError("NOT_FOUND", "产品不存在", status_code=404)
    return ProductRefiner(db, hotel_id).publish_check(product)


@router.post("/products/{product_id}/marketing-assets", response_model=ProductRead)
def regenerate_marketing_assets(
    product_id: int,
    request: MarketingRegenerationRequest | None = Body(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_hotel_user),
):
    hotel_id = hotel_id_for(db, user)
    product = get_product(db, product_id)
    if not product or product.hotel_id != hotel_id or product.status == "DELETED":
        raise AppError("NOT_FOUND", "产品不存在", status_code=404)
    options = request or MarketingRegenerationRequest()
    ProductService(db, hotel_id).regenerate_marketing(product, style=options.style, generate_image=options.generate_image)
    db.commit()
    return product_to_dict(product)


@router.post("/products/refine-marketing", response_model=list[ProductRead])
def refine_generated_product_marketing(
    request: BatchMarketingRefinementRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_hotel_user),
):
    """Apply one operator instruction to several generated product candidates.

    This is deliberately constrained to the creative surface.  The hotel can
    use language such as “改成更适合带娃的轻松种草口吻”，while FastAPI keeps
    all real allocations and prices untouched and therefore still valid.
    """

    hotel_id = hotel_id_for(db, user)
    ordered_ids = list(dict.fromkeys(request.product_ids))
    if len(ordered_ids) != len(request.product_ids):
        raise AppError("VALIDATION_ERROR", "请不要重复选择同一套候选产品", field="product_ids")
    products = [get_product(db, product_id) for product_id in ordered_ids]
    if any(not product or product.hotel_id != hotel_id or product.status == "DELETED" for product in products):
        raise AppError("NOT_FOUND", "存在不可编辑的产品候选", status_code=404)

    service = ProductService(db, hotel_id)
    for product in products:
        service.regenerate_marketing(
            product,
            creative_direction=request.natural_language,
            style=request.style,
            generate_image=request.generate_image,
        )
    db.commit()
    return [product_to_dict(product) for product in products]


@router.delete("/products/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    hotel_id = hotel_id_for(db, user)
    product = get_product(db, product_id)
    if not product or product.hotel_id != hotel_id or product.status == "DELETED":
        raise AppError("NOT_FOUND", "产品不存在", status_code=404)
    intent_count = db.scalar(select(func.count(VisitorIntent.id)).where(VisitorIntent.product_id == product.id)) or 0
    if intent_count:
        product.status = "DELETED"
        db.commit()
        return {"deleted": True, "archived": True, "message": "产品已有预约意向，已安全归档并从产品池移除"}
    db.delete(product)
    db.commit()
    return {"deleted": True, "archived": False, "message": "产品已删除"}


@router.patch("/products/{product_id}/status", response_model=ProductRead)
def product_status(product_id: int, request: ProductStatusRequest, db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    product = get_product(db, product_id)
    if not product or product.hotel_id != hotel_id_for(db, user):
        raise AppError("NOT_FOUND", "产品不存在", status_code=404)
    if product.status == "PENDING_CONFIRMATION":
        raise AppError("PROPOSAL_CONFIRMATION_REQUIRED", "请先在 AI 运营任务中确认该候选，再调整产品状态。", status_code=409)
    if request.status == "ON_SALE":
        if product.target_date < date.today():
            raise AppError("PRODUCT_DATE_PASSED", "产品出行日期已结束，不能重新上架；请调整出行日期并重新校验后发布。", status_code=409)
        ProductService(db, hotel_id_for(db, user)).ensure_publish_capacity(product)
        if product.sale_quantity <= 0:
            raise AppError("CAPACITY_INSUFFICIENT", "库存为0的产品不能发布", field="status")
        product.status = "LOW_STOCK" if product.sale_quantity <= 2 else "ON_SALE"
    else:
        product.status = request.status
    db.commit()
    return product_to_dict(product)


@router.get("/products/{product_id}/adjustments", response_model=list[AdjustmentRead])
def product_adjustments(product_id: int, db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    product = get_product(db, product_id)
    if not product or product.hotel_id != hotel_id_for(db, user):
        raise AppError("NOT_FOUND", "产品不存在", status_code=404)
    return product.adjustments


@router.get("/changes")
def changes(db: Session = Depends(get_db), user: User = Depends(get_hotel_user), limit: int = Query(default=50, ge=1, le=200)):
    hotel_id = hotel_id_for(db, user)
    # Order reservations belong in the order view; they are not resource edits
    # and created repeated room/experience rows in the operations feed.
    items = list(db.scalars(select(ResourceChangeEvent).where(
        ResourceChangeEvent.hotel_id == hotel_id,
        ResourceChangeEvent.event_type != "VISITOR_INTENT_RESERVED",
    ).order_by(ResourceChangeEvent.created_at.desc()).limit(limit)).all())
    return [{"id": item.id, "event_type": item.event_type, "resource_type": item.resource_type, "resource_id": item.resource_id, "old_value": item.old_value, "new_value": item.new_value, "reason": item.reason, "processed": item.processed, "processing_result": item.processing_result, "created_at": item.created_at} for item in items]


@router.get("/intents")
def intents(db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    hotel_id = hotel_id_for(db, user)
    sweep_expired_intents(db, hotel_id)
    db.commit()
    items = list(
        db.scalars(
            select(VisitorIntent)
            .join(TravelProduct)
            .options(selectinload(VisitorIntent.product))
            .where(TravelProduct.hotel_id == hotel_id)
            .order_by(VisitorIntent.created_at.desc())
        ).all()
    )
    return [
        {
            "id": item.id,
            "product_id": item.product_id,
            "product_name": item.product.product_name if item.product else "已归档产品",
            "product_code": item.product.product_code if item.product else None,
            "target_date": item.product.target_date if item.product else None,
            "product_status": item.product.status if item.product else None,
            "remaining_quantity": item.product.sale_quantity if item.product else 0,
            "submitted_price": (item.recommendation_result or {}).get("submitted_price") if item.recommendation_result else None,
            "adult_count": item.adult_count,
            "child_count": item.child_count,
            "child_ages": item.child_ages,
            "natural_language": item.natural_language,
            "budget": item.budget,
            "interests": item.interests,
            "negative_interests": item.negative_interests,
            "activity_level": item.activity_level,
            "dietary_restrictions": item.dietary_restrictions,
            "allergy_information": item.allergy_information,
            "arrival_time": item.arrival_time,
            "preferred_experience_time": item.preferred_experience_time,
            "other_requirements": item.other_requirements,
            "recommendation_result": item.recommendation_result,
            "intent_status": item.intent_status,
            "reservation_status": item.reservation_status,
            "reserved_until": item.reserved_until,
            "released_at": item.released_at,
            "confirmed_at": item.confirmed_at,
            "contact_name": item.contact_name,
            "contact_phone": item.contact_phone,
            "created_at": item.created_at,
        }
        for item in items
    ]


@router.patch("/intents/{intent_id}")
async def update_intent_status(intent_id: int, request: VisitorIntentStatusUpdate, db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    hotel_id = hotel_id_for(db, user)
    sweep_expired_intents(db, hotel_id)
    intent = db.scalar(
        select(VisitorIntent)
        .join(TravelProduct)
        .options(selectinload(VisitorIntent.product))
        .where(VisitorIntent.id == intent_id, TravelProduct.hotel_id == hotel_id)
        .with_for_update()
    )
    if not intent:
        raise AppError("NOT_FOUND", "预约意向不存在", status_code=404)
    if request.status == "CONFIRMED":
        if intent.reservation_status not in {"HELD", "CONFIRMED"}:
            raise AppError("INTENT_NOT_ACTIVE", "该预约意向已释放或过期，不能确认")
        intent.reservation_status = "CONFIRMED"
        intent.intent_status = "CONFIRMED"
        intent.confirmed_at = datetime.now(timezone.utc)
        message = "预约意向已确认，底层资源继续保持占用"
    else:
        if intent.reservation_status in {"HELD", "CONFIRMED"}:
            release_intent_inventory(db, intent)
            if intent.product:
                reconcile_published_capacity(db, intent.product.hotel_id)
        intent.reservation_status = "RELEASED"
        intent.intent_status = "CANCELLED"
        message = "预约意向已取消，底层房量、服务和合作名额已释放"
    db.commit()
    await manager.broadcast(hotel_id, {"type": "VISITOR_INTENT_UPDATED", "title": "预约意向状态更新", "message": message, "affectedProducts": [{"product_id": intent.product_id, "new_quantity": intent.product.sale_quantity if intent.product else None}]})
    return {"id": intent.id, "intent_status": intent.intent_status, "reservation_status": intent.reservation_status, "message": message}


@router.get("/skill-logs")
def skill_logs(db: Session = Depends(get_db), user: User = Depends(get_hotel_user), limit: int = Query(default=50, ge=1, le=200)):
    hotel_id = hotel_id_for(db, user)
    items = list(db.scalars(select(SkillCallLog).where(SkillCallLog.hotel_id == hotel_id).order_by(SkillCallLog.created_at.desc()).limit(limit)).all())
    return items


@router.get("/agent-diagnostics")
def agent_diagnostics(db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    """Expose safe Agent wiring details to hotel operators, never credentials."""
    is_remote = settings.agent_provider.lower() == "openclaw"
    configured = is_remote and bool(settings.openclaw_base_url and settings.openclaw_gateway_token and settings.openclaw_agent_id)
    gateway = {
        "configured": configured,
        "reachable": False,
        "status_code": None,
        "error": "OpenClaw Gateway not configured" if is_remote else "Demo mode uses Mock Agent",
    }
    if configured:
        agent = OpenClawAgent(settings.openclaw_base_url, settings.openclaw_gateway_token, settings.openclaw_agent_target, settings.agent_timeout_seconds, transport=settings.openclaw_transport, responses_path=settings.openclaw_responses_path, agent_id=settings.openclaw_agent_id, skill_version=settings.openclaw_skill_version, primary_model=settings.openclaw_primary_model)
        gateway = agent.diagnostics()
    provider = "OPENCLAW" if is_remote else "MOCK"
    skill_status = "READY" if is_remote and settings.openclaw_live_ready else ("NOT_READY" if is_remote else "DEMO")
    return {
        "provider": provider,
        "mode": settings.mode,
        "transport": settings.openclaw_transport if is_remote else "mock",
        "gateway": gateway,
        "agent_id": settings.openclaw_agent_id if is_remote else "",
        "agent_target": settings.openclaw_agent_target if is_remote else "",
        "primary_model": settings.openclaw_primary_model if is_remote else "",
        "live_ready": bool(is_remote and settings.openclaw_live_ready),
        "skills_discovered": bool(is_remote and settings.openclaw_skills_ready),
        "skill_status": skill_status,
         "skills": [
            {"name": "yusuchengjing-hotel-ops", "version": settings.openclaw_skill_version, "status": skill_status, "configured": settings.openclaw_skills_ready},
            {"name": "stayscape-product-generator", "version": settings.openclaw_skill_version, "status": skill_status, "configured": settings.openclaw_skills_ready},
            {"name": "stayscape-visitor-matcher", "version": settings.openclaw_skill_version, "status": skill_status, "configured": settings.openclaw_skills_ready},
            {"name": "stayscape-marketing-writer", "version": settings.openclaw_skill_version, "status": skill_status, "configured": settings.openclaw_skills_ready},
        ],
    }
