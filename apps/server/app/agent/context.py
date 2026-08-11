"""Request context shared by the web, visitor and Feishu entry points."""

from __future__ import annotations

from dataclasses import dataclass
import re


VALID_CHANNELS = {"WEB_VISITOR", "WEB_HOTEL", "FEISHU", "SYSTEM"}
VALID_ROLES = {"VISITOR", "HOTEL_OPERATOR", "HOTEL_SUPPORT", "HOTEL", "SYSTEM"}


def _safe_token(value: str | None) -> str:
    value = re.sub(r"[^a-zA-Z0-9_.:-]", "-", str(value or "").strip())
    return value[:120]


@dataclass(frozen=True)
class RequestContext:
    source_channel: str = "SYSTEM"
    actor_role: str = "SYSTEM"
    hotel_id: int | None = None
    user_id: int | None = None
    conversation_id: str | None = None
    trace_id: str | None = None

    def __post_init__(self) -> None:
        if self.source_channel not in VALID_CHANNELS:
            raise ValueError(f"unsupported source_channel: {self.source_channel}")
        if self.actor_role not in VALID_ROLES:
            raise ValueError(f"unsupported actor_role: {self.actor_role}")
        if self.source_channel == "WEB_VISITOR" and self.actor_role != "VISITOR":
            raise ValueError("WEB_VISITOR must use VISITOR actor_role")
        if self.source_channel in {"WEB_HOTEL", "FEISHU"} and self.hotel_id is None:
            raise ValueError("hotel context is required for hotel and Feishu calls")

    @property
    def session_key(self) -> str | None:
        """Return an isolated OpenClaw session key, or None for stateless calls."""
        conversation = _safe_token(self.conversation_id)
        if not conversation:
            return None
        if self.source_channel == "WEB_VISITOR":
            return f"visitor:{conversation}"
        if self.source_channel == "WEB_HOTEL":
            return f"hotel:{self.hotel_id}:{conversation}"
        if self.source_channel == "FEISHU":
            return f"feishu:{self.hotel_id}:{conversation}"
        return None

