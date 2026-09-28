from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Body, Depends, File, Query, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ...core.exceptions import AppError
from ...core.security import create_websocket_ticket
from ...config import settings
from ...db import get_db
from ...models import AgentApiToken, AgentConversation, Hotel, HotelService, Merchant, PartnerResource, ProductProposal, ProductResource, ResourceChangeEvent, RoomInventory, SkillCallLog, TravelProduct, User, VisitorIntent
from ...repositories.product_repository import get_product, list_products
from ...repositories.resource_repository import list_partner_resources, list_rooms, list_services
from ...schemas.dashboard import DashboardResponse
from ...schemas.products import AdjustmentRead, BatchMarketingRefinementRequest, GenerateProductRequest, MarketingRegenerationRequest, ProductDetailResponse, ProductDraftInterpretRequest, ProductDraftInterpretResponse, ProductGenerateResponse, ProductListResponse, ProductRead, ProductRefineRequest, ProductRefineResponse, ProductStatusRequest, ProductUpdateRequest, ResourceChangeResponse
from ...schemas.ai_operations import AssistantConversationCreate, AssistantMessageCreate, AgentConversationRead, AssistantTaskResponse, ProductProposalRead, ProposalConfirmRequest
from ...schemas.ai_operations import OrderOverviewResponse, SalesCommandRequest, SalesCommandResponse
from ...schemas.visitor import VisitorIntentStatusUpdate
from ...schemas.resources import MediaImportRequest, MediaSearchRequest, MerchantRead, PackageToggleRequest, PartnerResourceRead, ResourceMediaUpdate, RoomCreate, RoomRead, RoomUpdate, ServiceCreate, ServiceRead, ServiceUpdate
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
from ...services.serializers import partner_resource_to_dict, product_to_dict
from ...services.media_library_service import MAX_MEDIA_BYTES, MediaLibraryService
from ...services.agent_token_service import create_token, list_tokens, revoke_token
from ...agent.openclaw import OpenClawAgent
from ...agent.context import RequestContext
from ..deps import get_hotel_user, resolve_hotel_id
from ..websocket_manager import manager

router = APIRouter(prefix="/hotel", tags=["hotel"])


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


def proposal_to_dict(db: Session, proposal: ProductProposal) -> dict:
    """Serialize only auditable task state, never an Agent reasoning trace."""
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
        "product": product_to_dict(product) if product else None,
    }


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
def ai_conversations(db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    hotel_id = hotel_id_for(db, user)
    return list(db.scalars(select(AgentConversation).where(AgentConversation.hotel_id == hotel_id).order_by(AgentConversation.updated_at.desc()).limit(30)).all())


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
    return {"conversation": conversation, "proposals": [proposal_to_dict(db, item) for item in proposals], "message": "已生成待确认候选；确认后才会进入草稿或对游客发布。"}


@router.get("/ai/proposals", response_model=list[ProductProposalRead])
def ai_proposals(status: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    hotel_id = hotel_id_for(db, user)
    context = RequestContext(source_channel="WEB_HOTEL", actor_role="HOTEL_OPERATOR", hotel_id=hotel_id, user_id=user.id)
    return [proposal_to_dict(db, item) for item in ProductProposalService(db, hotel_id, context).list_proposals(status=status)]


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
def ai_overview(target_date: date | None = None, db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    """One compact, review-friendly view of facts used by hotel AI tasks."""
    hotel_id = hotel_id_for(db, user)
    selected_date = target_date or date.today()
    proposals = list(db.scalars(select(ProductProposal).where(ProductProposal.hotel_id == hotel_id, ProductProposal.status == "PENDING_CONFIRMATION")).all())
    insights = OperationsInsightService(db, hotel_id)
    # 待确认队列里很多是历史候选，单独给出今日新增，避免顶部指标看起来过于沉重。
    pending_today = sum(
        1
        for item in proposals
        if item.created_at is not None and item.created_at.date() == selected_date
    )
    return {
        "operations_insights": insights.snapshot(target_date=selected_date),
        # 顶部指标：未来 10 天的未售房量、压力最大的房型和重点日期可组包资源数。
        "inventory_pressure": insights.room_night_pressure(window_days=10),
        "weather": WeatherService(db).get_forecast("杭州", selected_date),
        "knowledge": KnowledgeService(db).search(limit=12),
        "knowledge_total": KnowledgeService(db).total(),
        "pending_confirmation_count": len(proposals),
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

    _ = (db, user)
    return public_settings()


@router.put("/settings/integrations")
def update_hotel_settings(payload: IntegrationSettingsUpdate, db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    """Save operator overrides for the model, vision and image services."""

    _ = (db, user)
    save_settings(payload.model_dump(exclude_none=True))
    return public_settings()


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
        "disclosure": "",
    }


@router.post("/knowledge/refresh")
def refresh_hotel_knowledge(db: Session = Depends(get_db), user: User = Depends(get_hotel_user)):
    """Re-check each stored source page and stamp the records that respond."""

    _ = user
    result = KnowledgeService(db).refresh_sources(city="杭州")
    db.commit()
    return result


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
    previous_step = str((conversation.last_execution or {}).get("step") or "")

    advisor = ProductAdvisor(db, hotel_id)
    answer = advisor.respond(request.natural_language, state)
    summary_text = str(answer.get("summary") or "").strip()
    step = str(answer.get("step") or "")
    # OVERVIEW 每轮读的都是同一批经营数据，长总结会和上一轮几乎重复，不再逐轮塞进
    # 对话记录；当前结论由前端根据 advisor.answer 渲染。只有状态变化才写入历史。
    if summary_text and step != "OVERVIEW":
        messages.append({"role": "assistant", "content": summary_text[:2000], "created_at": datetime.now(timezone.utc).isoformat()})
        conversation.messages = messages[-50:]
    plan = dict(answer.get("plan") or {})
    # 记住当前选中的体验，下一轮预算达不到时保持它不变，而不是悄悄换资源。
    selected_experiences = ((answer.get("primary") or {}).get("experiences") or [])
    if selected_experiences:
        plan["selected_resource"] = str(selected_experiences[0].get("name") or "")
    conversation.last_execution = {
        "advisor": plan,
        "step": step,
        "at": datetime.now(timezone.utc).isoformat(),
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
            generate_request = GenerateProductRequest(
                target_date=room.available_date,
                weather="CLOUDY",
                target_crowd=crowd_code,
                party_size=int(plan.get("party_size") or 2),
                theme=theme[:60],
                room_inventory_id=room.id,
                variant_count=3,
                creative_direction=" ".join(str(item) for item in (plan.get("resources") or []))[:400],
            )
            service = ProductProposalService(
                db,
                hotel_id,
                RequestContext(source_channel="WEB_HOTEL", actor_role="HOTEL_OPERATOR", hotel_id=hotel_id, user_id=user.id, conversation_id=str(conversation.id)),
            )
            proposals = service.create_from_request(generate_request, conversation=conversation, natural_language=request.natural_language)
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
            .options(selectinload(VisitorIntent.product))
            .where(TravelProduct.hotel_id == hotel_id)
            .order_by(VisitorIntent.created_at.desc())
        ).unique().all()
    )
    confirmed = [item for item in intents if item.reservation_status == "CONFIRMED"]
    held = [item for item in intents if item.reservation_status == "HELD"]
    cancelled = [item for item in intents if item.reservation_status == "CANCELLED"]
    revenue = sum((item.product.suggested_price for item in confirmed if item.product), Decimal("0"))

    crowd_labels = {
        "FAMILY": "亲子家庭", "COUPLE": "两人同行", "FRIENDS": "朋友出行",
        "SOLO": "独自旅行", "LOCAL_WEEKEND": "本地周末", "ALL": "不限客群",
    }
    buckets: dict[str, dict[str, Any]] = {}
    order_rows: list[dict[str, Any]] = []
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
        if intent.reservation_status == "CONFIRMED":
            bucket["confirmed"] += 1
            bucket["revenue"] += Decimal(str(product.suggested_price or 0))
        order_rows.append(
            {
                "id": intent.id,
                "product_name": product.product_name,
                "category": category,
                "amount": str(product.suggested_price),
                "target_date": product.target_date.isoformat(),
                "status": {"CONFIRMED": "已成交", "HELD": "待确认", "CANCELLED": "已取消"}.get(str(intent.reservation_status), "已处理"),
                "contact_name": intent.contact_name,
                "contact_phone": intent.contact_phone,
                "note": intent.other_requirements,
            }
        )

    return {
        "total": len(intents),
        "confirmed": len(confirmed),
        "held": len(held),
        "cancelled": len(cancelled),
        "confirmed_revenue": str(revenue),
        "categories": [
            {"label": bucket["label"], "count": bucket["count"], "confirmed": bucket["confirmed"], "revenue": str(bucket["revenue"])}
            for bucket in sorted(buckets.values(), key=lambda row: row["count"], reverse=True)
        ],
        "orders": order_rows[:40],
    }


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
    sweep_expired_intents(db, hotel_id)
    db.commit()
    hotel = db.get(Hotel, hotel_id)
    today = date.today()
    target = today + timedelta(days=1)
    rooms = list_rooms(db, hotel_id)
    resources = list_partner_resources(db, hotel_id)
    products = list_products(db, hotel_id)
    hotel_intents = list(
        db.scalars(
            select(VisitorIntent)
            .join(TravelProduct)
            .options(selectinload(VisitorIntent.product))
            .where(TravelProduct.hotel_id == hotel_id)
        ).all()
    )
    intents = len(hotel_intents)
    active_statuses = {"ON_SALE", "LOW_STOCK"}
    active_products = [item for item in products if item.status in active_statuses]
    confirmed = [item for item in hotel_intents if item.reservation_status == "CONFIRMED" and item.product]
    held = [item for item in hotel_intents if item.reservation_status == "HELD" and item.product]
    zero = Decimal("0")
    confirmed_revenue = sum((item.product.suggested_price for item in confirmed if item.product), zero)
    confirmed_gross_profit = sum((item.product.gross_profit for item in confirmed if item.product), zero)
    held_revenue = sum((item.product.suggested_price for item in held if item.product), zero)
    available_package_count = sum(max(0, item.sale_quantity) for item in active_products)
    listed_value = sum((item.suggested_price * max(0, item.sale_quantity) for item in active_products), zero)

    # Keep the revenue series factual: confirmed bookings are income, while
    # held reservations remain visible separately and never inflate sales.
    timeline_dates = {today - timedelta(days=offset) for offset in range(6, -1, -1)}
    timeline_dates.update(item.target_date for item in active_products if item.target_date >= today)
    timeline_dates.update(
        item.confirmed_at.date()
        for item in confirmed
        if item.confirmed_at is not None
    )
    timeline: dict[date, dict] = {
        value: {
            "date": value.isoformat(),
            "confirmed_orders": 0,
            "confirmed_revenue": zero,
            "confirmed_gross_profit": zero,
            "on_sale_products": 0,
            "available_packages": 0,
            "listed_value": zero,
        }
        for value in sorted(timeline_dates)
    }
    for product in active_products:
        point = timeline.setdefault(product.target_date, {
            "date": product.target_date.isoformat(), "confirmed_orders": 0,
            "confirmed_revenue": zero, "confirmed_gross_profit": zero,
            "on_sale_products": 0, "available_packages": 0, "listed_value": zero,
        })
        point["on_sale_products"] += 1
        point["available_packages"] += max(0, product.sale_quantity)
        point["listed_value"] += product.suggested_price * max(0, product.sale_quantity)
    for intent in confirmed:
        if not intent.product or not intent.confirmed_at:
            continue
        value = intent.confirmed_at.date()
        point = timeline.setdefault(value, {
            "date": value.isoformat(), "confirmed_orders": 0,
            "confirmed_revenue": zero, "confirmed_gross_profit": zero,
            "on_sale_products": 0, "available_packages": 0, "listed_value": zero,
        })
        point["confirmed_orders"] += 1
        point["confirmed_revenue"] += intent.product.suggested_price
        point["confirmed_gross_profit"] += intent.product.gross_profit
    changes = list(db.scalars(select(ResourceChangeEvent).where(ResourceChangeEvent.hotel_id == hotel_id).order_by(ResourceChangeEvent.created_at.desc()).limit(6)).all())
    return {
        "hotel_id": hotel_id,
        "hotel_name": hotel.name if hotel else "StayScape",
        "target_date": target.isoformat(),
        "room_count": len(rooms),
        "expiring_room_count": sum(1 for item in rooms if item.available_date == target),
        "available_room_units": sum(max(0, item.available_count) for item in rooms if item.available_date == target),
        "partner_resource_count": len(resources),
        "package_enabled_resource_count": sum(1 for item in resources if item.package_enabled and item.status == "AVAILABLE"),
        "product_count": len(products),
        "on_sale_product_count": len(active_products),
        "low_stock_product_count": sum(1 for item in products if item.status == "LOW_STOCK"),
        "visitor_intent_count": int(intents),
        "gross_profit_on_sale": sum((item.gross_profit * item.sale_quantity for item in active_products), zero),
        "confirmed_order_count": len(confirmed),
        "confirmed_revenue": confirmed_revenue,
        "confirmed_gross_profit": confirmed_gross_profit,
        "held_order_count": len(held),
        "held_revenue": held_revenue,
        "available_package_count": available_package_count,
        "listed_value": listed_value,
        "sales_timeline": [timeline[value] for value in sorted(timeline)],
        "recent_changes": [{"id": item.id, "event_type": item.event_type, "resource_type": item.resource_type, "resource_id": item.resource_id, "reason": item.reason, "processed": item.processed, "created_at": item.created_at} for item in changes],
    }


@router.get("/rooms", response_model=list[RoomRead])
def rooms(db: Session = Depends(get_db), user: User = Depends(get_hotel_user), target_date: date | None = Query(default=None)):
    hotel_id = hotel_id_for(db, user)
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


@router.get("/products", response_model=ProductListResponse)
def products(db: Session = Depends(get_db), user: User = Depends(get_hotel_user), status: str | None = None):
    items = list_products(db, hotel_id_for(db, user))
    if status:
        items = [item for item in items if item.status == status]
    else:
        # A generated candidate is not a hotel product yet. It becomes visible
        # in this list only after the operator confirms draft or publish.
        items = [item for item in items if item.status != "PENDING_CONFIRMATION"]
    return {"items": [product_to_dict(item) for item in items], "total": len(items)}


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
    return product_to_dict(product, include_adjustments=True)


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

    changed = request.model_dump(exclude_unset=True, exclude={"regenerate_marketing", "target_date", "room_inventory_id", "marketing_assets"})
    if request.target_date is not None:
        changed["target_date"] = target_date
    if request.room_inventory_id is not None or target_date != product.target_date:
        changed["room_inventory_id"] = room_id
    if target_date != product.target_date:
        forecast = WeatherService(db).get_forecast("杭州", target_date)
        if forecast.get("usable"):
            changed["weather"] = str(forecast.get("scenario") or product.weather)
        else:
            note = "天气信息需确认，请以出发前最新预报为准。"
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
    db.flush()

    service = ProductService(db, hotel_id)
    if weather_or_context_changed:
        service.recalculate_product(product)
        reconcile_published_capacity(db, hotel_id, priority_product_id=product.id if product.status in {"ON_SALE", "LOW_STOCK"} else None)
    if request.regenerate_marketing or any(key in changed for key in ("theme", "weather", "target_crowd")):
        service.regenerate_marketing(product)
    db.commit()
    return product_to_dict(product)


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
    return {**result, "product": product_to_dict(product)}


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
    resource_ids = [item.id for item in list_partner_resources(db, hotel_id)]
    items = list(db.scalars(select(ResourceChangeEvent).where(ResourceChangeEvent.hotel_id == hotel_id).order_by(ResourceChangeEvent.created_at.desc()).limit(limit)).all())
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
