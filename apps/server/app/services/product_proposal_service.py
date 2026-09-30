"""Auditable, human-confirmed hotel product proposals.

Both Hotel Web and Feishu call this service.  It deliberately puts an Agent
result in ``PENDING_CONFIRMATION`` first: an LLM may suggest a product, but a
hotel operator must explicitly choose draft or publish after FastAPI has
revalidated real inventory, price and time constraints.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agent import AgentOrchestrator
from ..agent.context import RequestContext
from ..core.exceptions import AppError
from ..models import AgentConversation, ProductProposal, RoomInventory, SkillCallLog, TravelProduct
from ..schemas.products import GenerateProductRequest
from .product_draft_parser import interpret_product_draft
from .product_service import ProductService


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _public_step(name: str, status: str, detail: str) -> dict[str, str]:
    """A concise audit event; never a model hidden-reasoning trace."""
    return {"name": name, "status": status, "detail": detail, "at": _now().isoformat()}


class ProductProposalService:
    def __init__(self, db: Session, hotel_id: int, context: RequestContext) -> None:
        self.db = db
        self.hotel_id = hotel_id
        self.context = context

    def conversation(self, *, external_id: str = "", title: str = "酒店 AI 运营任务") -> AgentConversation:
        external_id = external_id.strip()[:180]
        existing = None
        if external_id:
            existing = self.db.scalar(
                select(AgentConversation).where(
                    AgentConversation.hotel_id == self.hotel_id,
                    AgentConversation.source_channel == self.context.source_channel,
                    AgentConversation.external_conversation_id == external_id,
                    AgentConversation.status == "ACTIVE",
                )
            )
        if existing:
            return existing
        item = AgentConversation(
            hotel_id=self.hotel_id,
            source_channel=self.context.source_channel,
            actor_role=self.context.actor_role,
            external_conversation_id=external_id,
            title=(title.strip() or "酒店 AI 运营任务")[:220],
            messages=[],
            last_execution=None,
        )
        self.db.add(item)
        self.db.flush()
        return item

    @staticmethod
    def _append_message(conversation: AgentConversation, role: str, content: str) -> None:
        messages = list(conversation.messages or [])
        messages.append({"role": role, "content": content[:3000], "created_at": _now().isoformat()})
        conversation.messages = messages[-50:]

    def _available_target_date(self, requested: date, party_size: int) -> date:
        room = self.db.scalar(
            select(RoomInventory.id).where(
                RoomInventory.hotel_id == self.hotel_id,
                RoomInventory.available_date == requested,
                RoomInventory.available_count > 0,
                RoomInventory.max_guests >= party_size,
                RoomInventory.status.not_in({"SOLD_OUT", "DISABLED"}),
            )
        )
        if room:
            return requested
        next_date = self.db.scalar(
            select(RoomInventory.available_date)
            .where(
                RoomInventory.hotel_id == self.hotel_id,
                RoomInventory.available_date >= date.today(),
                RoomInventory.available_count > 0,
                RoomInventory.max_guests >= party_size,
                RoomInventory.status.not_in({"SOLD_OUT", "DISABLED"}),
            )
            .order_by(RoomInventory.available_date)
        )
        return next_date or requested

    def request_from_language(self, natural_language: str) -> GenerateProductRequest:
        parsed = interpret_product_draft(natural_language)["interpreted"]
        requested = GenerateProductRequest.model_validate(parsed)
        parsed["target_date"] = self._available_target_date(requested.target_date, requested.party_size).isoformat()
        # Weather is resolved from the server-side provider below. A visitor or
        # operator sentence can express a preference, but cannot assert a fact.
        parsed["weather"] = "CLOUDY"
        return GenerateProductRequest.model_validate(parsed)

    def create_from_request(
        self,
        request: GenerateProductRequest,
        *,
        conversation: AgentConversation,
        natural_language: str = "",
    ) -> list[ProductProposal]:
        if self.context.actor_role != "HOTEL_OPERATOR":
            raise AppError("FORBIDDEN", "只有酒店经营者可以创建待确认产品候选", status_code=403)
        orchestrator = AgentOrchestrator(self.db, hotel_id=self.hotel_id, context=self.context)
        service = ProductService(self.db, self.hotel_id, orchestrator=orchestrator)
        generated = service.generate_many(
            request,
            initial_status="PENDING_CONFIRMATION",
            natural_language=natural_language,
        )
        # AgentOrchestrator records one concise SkillCallLog per candidate.
        # Flush before reading it so the audit panel can report elapsed time
        # and the real fallback outcome without showing private prompts or
        # model reasoning.
        self.db.flush()
        trace_ids = [item[2] for item in generated]
        call_logs = list(
            self.db.scalars(
                select(SkillCallLog)
                .where(SkillCallLog.trace_id.in_(trace_ids))
                .order_by(SkillCallLog.created_at)
            ).all()
        )
        duration_ms = sum(max(0, int(item.duration_ms or 0)) for item in call_logs)
        # ProductService.generate_many returns
        # (product, output, trace_id, fallback_used) tuples.  Preserve the
        # per-candidate execution result in the public audit summary without
        # treating the tuple as a response object.
        fallback_used = any(item[3] for item in generated)
        intelligence = service.intelligence_context
        service_calls = [
            {"name": "实时库存与资源校验", "kind": "StayScape 服务", "status": "PASSED"},
            {"name": "近 14 天经营汇总", "kind": "StayScape 服务", "status": "CHECKED"},
            {"name": "天气预报", "kind": "StayScape 服务", "status": str((intelligence.get("weather") or {}).get("verification_status") or "VERIFY_REQUIRED")},
            {"name": "杭州文旅知识库", "kind": "StayScape 服务", "status": "CHECKED"},
        ]
        if self.context.source_channel == "FEISHU":
            # This is the narrow OpenClaw Tool that entered the shared
            # business service. The Web entry calls the same service directly,
            # so it must not pretend that a Tool was used.
            service_calls.insert(0, {"name": "stayscape_create_product_proposal", "kind": "OpenClaw Tool", "status": "PASSED"})
        steps = [
            _public_step("实时库存与资源校验", "PASSED", "已从酒店库存和合作资源中筛选可组合项。"),
            _public_step("近 14 天经营汇总", "CHECKED", "仅使用订单、销售额和资源余量的聚合信号，不读取游客个人信息。"),
            _public_step("天气信息", str((intelligence.get("weather") or {}).get("verification_status") or "VERIFY_REQUIRED"), str((intelligence.get("weather") or {}).get("advisory") or "天气信息需确认。")),
            _public_step("文旅知识库", "CHECKED", f"已检索 {len(intelligence.get('knowledge') or [])} 条带来源的文旅知识；未确认项不会被当作可售资源。"),
            _public_step("OpenClaw Agent + Product Skill", "PASSED", f"stayscape-main 调用 stayscape-product-generator 生成 {len(generated)} 个候选；Skill 耗时 {duration_ms}ms，并完成后端价格、容量、年龄、天气和时间冲突复核。"),
            _public_step("人工确认", "PENDING", "请确认加入草稿，或确认后直接发布；发布时会再次复核实时库存。"),
        ]
        proposals: list[ProductProposal] = []
        for product, _, trace_id, item_fallback_used in generated:
            proposal = ProductProposal(
                hotel_id=self.hotel_id,
                conversation_id=conversation.id,
                product_id=product.id,
                source_channel=self.context.source_channel,
                status="PENDING_CONFIRMATION",
                trace_ids=[trace_id],
                insight_snapshot=intelligence.get("insights"),
                weather_snapshot=intelligence.get("weather"),
                knowledge_snapshot=intelligence.get("knowledge") or [],
                execution_steps=steps + [_public_step("降级状态", "NONE" if not item_fallback_used else "FALLBACK", "正式 Live 模式不会自动降级；此记录仅说明本次实际执行状态。")],
            )
            self.db.add(proposal)
            proposals.append(proposal)
        self.db.flush()
        product_names = "、".join(item[0].product_name for item in generated[:3])
        self._append_message(conversation, "assistant", f"已生成 {len(proposals)} 个待确认候选：{product_names}。我已参考实时库存、天气、近 14 天经营聚合和带来源的文旅知识；请确认加入草稿或发布。")
        conversation.last_execution = {
            "agent": "stayscape-main",
            "skill": "stayscape-product-generator",
            "trace_ids": trace_ids,
            "tool_calls": service_calls,
            "used_weather": bool(intelligence.get("weather")),
            "used_knowledge": len(intelligence.get("knowledge") or []),
            "fallback_used": fallback_used,
            "duration_ms": duration_ms,
            "at": _now().isoformat(),
        }
        return proposals

    def create_from_language(
        self,
        natural_language: str,
        *,
        conversation: AgentConversation,
        variant_count: int | None = None,
    ) -> list[ProductProposal]:
        clean = natural_language.strip()
        if len(clean) < 2:
            raise AppError("VALIDATION_ERROR", "请用一句话描述希望生成的产品方向。", field="natural_language")
        # Multi-turn: an earlier sentence supplies the context, the newest
        # sentence is read first so a follow-up like "改成两个人" wins.
        history = [
            str(item.get("content", ""))
            for item in (conversation.messages or [])
            if isinstance(item, dict) and item.get("role") == "user"
        ][-3:]
        self._append_message(conversation, "user", clean)
        context_text = " ".join([clean, *history])[:800]
        request = self.request_from_language(context_text)
        if variant_count is not None:
            request = request.model_copy(update={"variant_count": max(1, min(3, int(variant_count)))})
        return self.create_from_request(request, conversation=conversation, natural_language=clean)

    def confirm(self, proposal_id: int, *, action: str, confirmed_by: str) -> ProductProposal:
        proposal = self.db.scalar(
            select(ProductProposal)
            .where(ProductProposal.id == proposal_id, ProductProposal.hotel_id == self.hotel_id)
            .with_for_update()
        )
        if not proposal:
            raise AppError("NOT_FOUND", "待确认产品不存在", status_code=404)
        if proposal.status != "PENDING_CONFIRMATION":
            raise AppError("PROPOSAL_ALREADY_DECIDED", "该候选已经完成确认，不能重复操作。", status_code=409)
        product = self.db.get(TravelProduct, proposal.product_id)
        if not product or product.status != "PENDING_CONFIRMATION":
            raise AppError("PROPOSAL_PRODUCT_INVALID", "待确认产品状态异常，请重新生成。", status_code=409)
        normalized = action.upper()
        if normalized not in {"DRAFT", "PUBLISH"}:
            raise AppError("VALIDATION_ERROR", "确认动作仅支持 DRAFT 或 PUBLISH。", field="action")
        if normalized == "PUBLISH":
            ProductService(self.db, self.hotel_id).ensure_publish_capacity(product)
            if product.sale_quantity <= 0:
                raise AppError("CAPACITY_INSUFFICIENT", "实时库存已不足，不能发布该产品。", field="action", retryable=True)
            product.status = "LOW_STOCK" if product.sale_quantity <= 2 else "ON_SALE"
            proposal.status = "PUBLISHED"
            detail = "经营者已确认发布；已完成发布前实时库存复核。"
        else:
            product.status = "DRAFT"
            proposal.status = "CONFIRMED_DRAFT"
            detail = "经营者已确认加入草稿；尚未面向游客展示。"
        proposal.confirmation_action = normalized
        proposal.confirmed_by = confirmed_by[:160]
        proposal.confirmed_at = _now()
        proposal.execution_steps = list(proposal.execution_steps or []) + [_public_step("人工确认", "PASSED", detail)]
        if proposal.conversation_id:
            conversation = self.db.get(AgentConversation, proposal.conversation_id)
            if conversation:
                self._append_message(conversation, "assistant", detail)
        self.db.flush()
        return proposal

    def proposal(self, proposal_id: int) -> ProductProposal:
        item = self.db.scalar(select(ProductProposal).where(ProductProposal.id == proposal_id, ProductProposal.hotel_id == self.hotel_id))
        if not item:
            raise AppError("NOT_FOUND", "待确认产品不存在", status_code=404)
        return item

    def list_proposals(
        self,
        *,
        status: str | None = None,
        conversation_id: int | None = None,
    ) -> list[ProductProposal]:
        query = select(ProductProposal).where(ProductProposal.hotel_id == self.hotel_id).order_by(ProductProposal.created_at.desc())
        if status:
            query = query.where(ProductProposal.status == status)
        if conversation_id is not None:
            query = query.where(ProductProposal.conversation_id == conversation_id)
        return list(self.db.scalars(query).all())
