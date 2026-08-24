import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from ..config import settings
from ..core.exceptions import AppError
from ..models import SkillCallLog
from .context import RequestContext
from .mock_agent import MockAgent
from .openclaw import OpenClawAgent
from .schemas import ProductAgentOutput, VisitorAgentOutput

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)

RETRYABLE_NETWORK_ERRORS = (TimeoutError, httpx.TimeoutException, httpx.TransportError, ConnectionError)


@dataclass(frozen=True)
class AgentCallResult:
    trace_id: str
    value: BaseModel
    raw_response: str
    status: str
    validation_result: dict[str, Any]
    retry_count: int
    fallback_used: bool
    provider: str = "MOCK"
    transport: str = "mock"
    agent_id: str = ""
    model: str = ""
    skill_version: str = ""


class AgentOrchestrator:
    """Route both Web entry points to one Agent and keep the fallback honest."""

    def __init__(
        self,
        db,
        provider: Any | None = None,
        hotel_id: int | None = None,
        *,
        context: RequestContext | None = None,
        source_channel: str | None = None,
        actor_role: str | None = None,
        user_id: int | None = None,
        conversation_id: str | None = None,
    ) -> None:
        self.db = db
        self.hotel_id = hotel_id
        self.context = context or RequestContext(
            source_channel=source_channel or ("WEB_HOTEL" if hotel_id is not None else "WEB_VISITOR"),
            actor_role=actor_role or ("HOTEL_OPERATOR" if hotel_id is not None else "VISITOR"),
            hotel_id=hotel_id,
            user_id=user_id,
            conversation_id=conversation_id,
        )
        if provider is not None:
            self.provider = provider
        elif settings.agent_provider.lower() == "openclaw":
            self.provider = OpenClawAgent(
                settings.openclaw_base_url,
                settings.openclaw_gateway_token,
                settings.openclaw_agent_target,
                settings.agent_timeout_seconds,
                transport=settings.openclaw_transport,
                responses_path=settings.openclaw_responses_path,
                agent_id=settings.openclaw_agent_id,
                skill_version=settings.openclaw_skill_version,
                primary_model=settings.openclaw_primary_model,
            )
        else:
            self.provider = MockAgent(settings.mock_agent_mode)

    @property
    def _live_without_fallback(self) -> bool:
        return settings.mode.lower() == "live" and getattr(self.provider, "provider_name", "MOCK") == "OPENCLAW"

    def _provider_generate(self, skill_name: str, payload: dict[str, Any], trace_id: str) -> str:
        if isinstance(self.provider, OpenClawAgent):
            return self.provider.generate(skill_name, payload, trace_id=trace_id, session_key=self.context.session_key)
        return self.provider.generate(skill_name, payload)

    def _provider_repair(self, skill_name: str, payload: dict[str, Any], raw: str, trace_id: str) -> str:
        if isinstance(self.provider, OpenClawAgent):
            return self.provider.repair_json(skill_name, payload, raw, trace_id=trace_id, session_key=self.context.session_key)
        return self.provider.repair_json(skill_name, payload, raw)

    def _request_with_retries(self, operation: Callable[[], str]) -> tuple[str, int]:
        retries = 0
        max_retries = max(0, settings.agent_max_retries)
        for attempt in range(max_retries + 1):
            try:
                return operation(), retries
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status not in {408, 429} and status < 500:
                    raise
                if attempt >= max_retries:
                    raise
                retries += 1
            except RETRYABLE_NETWORK_ERRORS:
                if attempt >= max_retries:
                    raise
                retries += 1
            time.sleep(min(0.25 * (2**attempt), 1.0))
        raise RuntimeError("agent request failed")

    def _log(
        self,
        *,
        trace_id: str,
        skill_name: str,
        scene: str,
        payload: dict[str, Any],
        raw: str,
        final_value: BaseModel | None,
        status: str,
        validation: dict[str, Any],
        error_code: str | None,
        error_message: str | None,
        duration_ms: int,
        retry_count: int,
        fallback_used: bool,
    ) -> None:
        provider = getattr(self.provider, "provider_name", "MOCK")
        self.db.add(
            SkillCallLog(
                trace_id=trace_id,
                hotel_id=self.hotel_id,
                skill_name=skill_name,
                business_scene=scene,
                request_json=payload,
                raw_response=raw,
                final_response=final_value.model_dump(mode="json") if final_value else None,
                call_status=status,
                validation_result=validation,
                error_code=error_code,
                error_message=error_message,
                duration_ms=duration_ms,
                retry_count=retry_count,
                provider=provider,
                source_channel=self.context.source_channel,
                actor_role=self.context.actor_role,
                transport=getattr(self.provider, "transport", "mock"),
                agent_id=getattr(self.provider, "agent_id", ""),
                model=getattr(self.provider, "primary_model", getattr(self.provider, "model", "")),
                skill_version=getattr(self.provider, "skill_version", ""),
                conversation_id=self.context.conversation_id or "",
                fallback_used=fallback_used,
            )
        )

    def _call(self, *, skill_name: str, scene: str, payload: dict[str, Any], schema: type[T], fallback_factory) -> AgentCallResult:
        trace_id = f"trace_{uuid.uuid4().hex}"
        started = time.perf_counter()
        raw = ""
        retry_count = 0
        status = "SUCCESS"
        validation: dict[str, Any] = {"valid": False, "errors": []}
        final_value: T | None = None
        error_code = None
        error_message = None
        fallback_used = False
        try:
            if self._live_without_fallback and not settings.openclaw_live_ready:
                status = "NOT_READY"
                error_code = "OPENCLAW_LIVE_NOT_READY"
                error_message = "OpenClaw Gateway, provider, Skills, tools, or smoke test is not ready"
            else:
                raw, retry_count = self._request_with_retries(lambda: self._provider_generate(skill_name, payload, trace_id))
            try:
                if raw:
                    final_value = schema.model_validate_json(raw)
                    validation = {"valid": True, "errors": []}
            except (ValidationError, ValueError, json.JSONDecodeError) as exc:
                validation = {"valid": False, "errors": [str(exc)]}
                if settings.agent_max_retries > 0:
                    retry_count += 1
                    raw, repair_retries = self._request_with_retries(lambda: self._provider_repair(skill_name, payload, raw, trace_id))
                    retry_count += repair_retries
                    final_value = schema.model_validate_json(raw)
                    validation = {"valid": True, "errors": [], "repaired": True}
                else:
                    status = "FORMAT_ERROR"
                    error_code = "AGENT_FORMAT_ERROR"
                    error_message = str(exc)
        except RETRYABLE_NETWORK_ERRORS as exc:
            status = "TIMEOUT" if isinstance(exc, (TimeoutError, httpx.TimeoutException)) else "FAILED"
            error_code = "AGENT_TIMEOUT" if status == "TIMEOUT" else "AGENT_CALL_FAILED"
            error_message = str(exc)
        except (httpx.HTTPStatusError, ValidationError, ValueError, json.JSONDecodeError) as exc:
            status = "FORMAT_ERROR" if isinstance(exc, (ValidationError, ValueError, json.JSONDecodeError)) else "FAILED"
            error_code = "AGENT_FORMAT_ERROR" if status == "FORMAT_ERROR" else "AGENT_CALL_FAILED"
            error_message = str(exc)
        except Exception as exc:
            status = "FAILED"
            error_code = "AGENT_CALL_FAILED"
            error_message = str(exc)

        duration_ms = int((time.perf_counter() - started) * 1000)
        if final_value is None and self._live_without_fallback:
            self._log(
                trace_id=trace_id, skill_name=skill_name, scene=scene, payload=payload, raw=raw,
                final_value=None, status=status, validation=validation, error_code=error_code,
                error_message=error_message, duration_ms=duration_ms, retry_count=retry_count, fallback_used=False,
            )
            # Agent calls happen before domain mutations. Commit the diagnostic row so a live-mode
            # refusal remains visible to operators after FastAPI rolls back the request transaction.
            self.db.commit()
            logger.warning(
                "OpenClaw request failed trace=%s skill=%s status=%s code=%s detail=%s",
                trace_id, skill_name, status, error_code, (error_message or "")[:500],
            )
            raise AppError(
                "AGENT_UNAVAILABLE",
                "AI服务暂时未返回可用结果，请稍后重试",
                status_code=503,
                retryable=True,
                details={"trace_id": trace_id, "provider": "OPENCLAW", "status": status, "error_code": error_code},
            )

        if final_value is None:
            fallback_used = True
            status = "FALLBACK"
            fallback_value = fallback_factory()
            final_value = schema.model_validate(fallback_value) if isinstance(fallback_value, dict) else fallback_value

        duration_ms = int((time.perf_counter() - started) * 1000)
        self._log(
            trace_id=trace_id, skill_name=skill_name, scene=scene, payload=payload, raw=raw,
            final_value=final_value, status=status, validation=validation, error_code=error_code,
            error_message=error_message, duration_ms=duration_ms, retry_count=retry_count, fallback_used=fallback_used,
        )
        return AgentCallResult(
            trace_id, final_value, raw, status, validation, retry_count, fallback_used,
            getattr(self.provider, "provider_name", "MOCK"), getattr(self.provider, "transport", "mock"),
            getattr(self.provider, "agent_id", ""),
            getattr(self.provider, "primary_model", getattr(self.provider, "model", "")),
            getattr(self.provider, "skill_version", ""),
        )

    def generate_product(self, payload: dict[str, Any]) -> AgentCallResult:
        return self._call(
            skill_name="stayscape-product-generator",
            scene="product_generation",
            payload=payload,
            schema=ProductAgentOutput,
            fallback_factory=lambda: MockAgent()._product(payload),
        )

    def match_visitor(self, payload: dict[str, Any]) -> AgentCallResult:
        return self._call(
            skill_name="stayscape-visitor-matcher",
            scene="visitor_matching",
            payload=payload,
            schema=VisitorAgentOutput,
            fallback_factory=lambda: MockAgent()._visitor(payload),
        )
