import json
import time
import uuid
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from ..config import settings
from ..models import SkillCallLog
from .mock_agent import MockAgent
from .openclaw import OpenClawAgent
from .schemas import ProductAgentOutput, VisitorAgentOutput

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class AgentCallResult:
    trace_id: str
    value: BaseModel
    raw_response: str
    status: str
    validation_result: dict[str, Any]
    retry_count: int
    fallback_used: bool


class AgentOrchestrator:
    def __init__(self, db, provider: Any | None = None) -> None:
        self.db = db
        if provider is not None:
            self.provider = provider
        elif settings.agent_provider.lower() == "openclaw" and settings.openclaw_base_url:
            self.provider = OpenClawAgent(settings.openclaw_base_url, settings.openclaw_api_key, settings.openclaw_model, settings.agent_timeout_seconds)
        else:
            self.provider = MockAgent(settings.mock_agent_mode)

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
            raw = self.provider.generate(skill_name, payload)
            try:
                final_value = schema.model_validate_json(raw)
                validation = {"valid": True, "errors": []}
            except (ValidationError, ValueError, json.JSONDecodeError) as exc:
                validation = {"valid": False, "errors": [str(exc)]}
                if retry_count < settings.agent_max_retries:
                    retry_count += 1
                    raw = self.provider.repair_json(skill_name, payload, raw)
                    final_value = schema.model_validate_json(raw)
                    validation = {"valid": True, "errors": [], "repaired": True}
                else:
                    status = "FORMAT_ERROR"
                    error_code = "AGENT_FORMAT_ERROR"
                    error_message = str(exc)
        except TimeoutError as exc:
            status = "TIMEOUT"
            error_code = "AGENT_TIMEOUT"
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
            )
        )
        return AgentCallResult(trace_id, final_value, raw, status, validation, retry_count, fallback_used)

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

