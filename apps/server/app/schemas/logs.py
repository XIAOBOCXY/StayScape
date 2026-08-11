from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class SkillLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    trace_id: str
    skill_name: str
    business_scene: str
    request_json: dict[str, Any] | None
    raw_response: str
    final_response: dict[str, Any] | None
    call_status: str
    validation_result: dict[str, Any] | None
    error_code: str | None
    error_message: str | None
    duration_ms: int
    retry_count: int
    provider: str
    source_channel: str
    actor_role: str
    transport: str
    agent_id: str
    model: str
    skill_version: str
    conversation_id: str
    fallback_used: bool
    created_at: datetime
