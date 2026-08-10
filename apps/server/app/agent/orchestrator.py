import json
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from ..config import settings
from ..models import SkillCallLog
from .mock_agent import MockAgent
from .openclaw import ClawHiveAgent, OpenClawAgent
from .schemas import ProductAgentOutput, VisitorAgentOutput

T = TypeVar("T", bound=BaseModel)
NETWORK_ERRORS = (TimeoutError, httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError, ConnectionError)


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
    def __init__(self, db, provider: Any | None = None, hotel_id: int | None = None) -> None:
        self.db = db
        self.hotel_id = hotel_id
        if provider is not None:
            self.provider = provider
        elif settings.agent_provider.lower() in {"openclaw", "clawhive"}:
            provider_name = settings.agent_provider.lower()
            is_clawhive = provider_name == "clawhive"
            base_url = (settings.clawhive_base_url or settings.openclaw_base_url) if is_clawhive else settings.openclaw_base_url
            api_key = (settings.clawhive_gateway_token or settings.clawhive_api_key or settings.openclaw_gateway_token or settings.openclaw_api_key) if is_clawhive else (settings.openclaw_gateway_token or settings.openclaw_api_key)
            model = (settings.clawhive_model or settings.openclaw_model) if is_clawhive else settings.openclaw_model
            transport = (settings.clawhive_transport or settings.openclaw_transport) if is_clawhive else settings.openclaw_transport
            responses_path = (settings.clawhive_responses_path or settings.openclaw_responses_path) if is_clawhive else settings.openclaw_responses_path
            agent_id = (settings.clawhive_agent_id or settings.openclaw_agent_id) if is_clawhive else settings.openclaw_agent_id
            skill_version = (settings.clawhive_skill_version or settings.openclaw_skill_version) if is_clawhive else settings.openclaw_skill_version
            agent_class = ClawHiveAgent if is_clawhive else OpenClawAgent
            if not base_url:
                self.provider = MockAgent(settings.mock_agent_mode)
                return
            self.provider = agent_class(
                base_url,
                api_key,
                model,
                settings.agent_timeout_seconds,
                transport=transport,
                responses_path=responses_path,
                invoke_path=settings.openclaw_invoke_path,
                tool_name=settings.openclaw_tool_name,
                session_key=settings.openclaw_session_key,
                agent_id=agent_id,
                skill_version=skill_version,
                legacy_fallback=settings.openclaw_legacy_fallback,
            )
        else:
            self.provider = MockAgent(settings.mock_agent_mode)

    def _provider_generate(self, skill_name: str, payload: dict[str, Any], trace_id: str) -> str:
        if isinstance(self.provider, OpenClawAgent):
            return self.provider.generate(skill_name, payload, trace_id=trace_id)
        return self.provider.generate(skill_name, payload)

    def _provider_repair(self, skill_name: str, payload: dict[str, Any], raw: str, trace_id: str) -> str:
        if isinstance(self.provider, OpenClawAgent):
            return self.provider.repair_json(skill_name, payload, raw, trace_id=trace_id)
        return self.provider.repair_json(skill_name, payload, raw)

    def _request_with_retries(self, operation: Callable[[], str]) -> tuple[str, int]:
        retries = 0
        last_error: Exception | None = None
        for attempt in range(max(0, settings.agent_max_retries) + 1):
            try:
                return operation(), retries
            except NETWORK_ERRORS as exc:
                last_error = exc
                if attempt >= max(0, settings.agent_max_retries):
                    raise
                retries += 1
                time.sleep(min(0.25 * (2**attempt), 1.0))
        raise last_error or RuntimeError("agent request failed")

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
        provider = getattr(self.provider, "provider_name", "MOCK")
        transport = getattr(self.provider, "transport", "mock")
        agent_id = getattr(self.provider, "agent_id", "")
        model = getattr(self.provider, "model", "")
        skill_version = getattr(self.provider, "skill_version", settings.openclaw_skill_version if provider == "OPENCLAW" else "")
        try:
            raw, request_retries = self._request_with_retries(lambda: self._provider_generate(skill_name, payload, trace_id))
            retry_count += request_retries
            try:
                final_value = schema.model_validate_json(raw)
                validation = {"valid": True, "errors": []}
            except (ValidationError, ValueError, json.JSONDecodeError) as exc:
                validation = {"valid": False, "errors": [str(exc)]}
                if settings.agent_max_retries > 0:
                    retry_count += 1  # the format repair is an explicit retry in the audit log
                    try:
                        raw, repair_retries = self._request_with_retries(lambda: self._provider_repair(skill_name, payload, raw, trace_id))
                        retry_count += repair_retries
                        final_value = schema.model_validate_json(raw)
                        validation = {"valid": True, "errors": [], "repaired": True}
                    except NETWORK_ERRORS as repair_exc:
                        status = "TIMEOUT" if isinstance(repair_exc, (TimeoutError, httpx.TimeoutException)) else "FAILED"
                        error_code = "AGENT_TIMEOUT" if status == "TIMEOUT" else "AGENT_CALL_FAILED"
                        error_message = str(repair_exc)
                    except (ValidationError, ValueError, json.JSONDecodeError) as repair_exc:
                        status = "FORMAT_ERROR"
                        error_code = "AGENT_FORMAT_ERROR"
                        error_message = str(repair_exc)
                else:
                    status = "FORMAT_ERROR"
                    error_code = "AGENT_FORMAT_ERROR"
                    error_message = str(exc)
        except NETWORK_ERRORS as exc:
            status = "TIMEOUT" if isinstance(exc, (TimeoutError, httpx.TimeoutException)) else "FAILED"
            error_code = "AGENT_TIMEOUT" if status == "TIMEOUT" else "AGENT_CALL_FAILED"
            error_message = str(exc)
        except Exception as exc:  # external adapters must never break the business transaction
            status = "FAILED"
            error_code = "AGENT_CALL_FAILED"
            error_message = str(exc)

        if final_value is None:
            fallback_used = True
            status = "FALLBACK"
            fallback_value = fallback_factory()
            final_value = schema.model_validate(fallback_value) if isinstance(fallback_value, dict) else fallback_value

        duration_ms = int((time.perf_counter() - started) * 1000)
        self.db.add(
            SkillCallLog(
                trace_id=trace_id,
                hotel_id=self.hotel_id,
                skill_name=skill_name,
                business_scene=scene,
                request_json=payload,
                raw_response=raw,
                final_response=final_value.model_dump(mode="json"),
                call_status=status,
                validation_result=validation,
                error_code=error_code,
                error_message=error_message,
                duration_ms=duration_ms,
                retry_count=retry_count,
                provider=provider,
                transport=transport,
                agent_id=agent_id,
                model=model,
                skill_version=skill_version,
                fallback_used=fallback_used,
            )
        )
        return AgentCallResult(trace_id, final_value, raw, status, validation, retry_count, fallback_used, provider, transport, agent_id, model, skill_version)

    def generate_product(self, payload: dict[str, Any]) -> AgentCallResult:
        def fallback() -> dict[str, Any]:
            return MockAgent()._product(payload)

        return self._call(
            skill_name="stayscape-product-generator",
            scene="product_generation",
            payload=payload,
            schema=ProductAgentOutput,
            fallback_factory=fallback,
        )

    def match_visitor(self, payload: dict[str, Any]) -> AgentCallResult:
        def fallback() -> dict[str, Any]:
            return MockAgent()._visitor(payload)

        return self._call(
            skill_name="stayscape-visitor-matcher",
            scene="visitor_matching",
            payload=payload,
            schema=VisitorAgentOutput,
            fallback_factory=fallback,
        )
