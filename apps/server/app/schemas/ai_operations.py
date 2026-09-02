"""Public, auditable schemas for hotel AI operations.

They intentionally describe only user-visible task state. Raw prompts, tokens,
gateway credentials and private model reasoning never leave the server logs.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .products import ProductRead


class AssistantConversationCreate(BaseModel):
    title: str = Field(default="酒店 AI 运营任务", min_length=1, max_length=220)


class AssistantMessageCreate(BaseModel):
    natural_language: str = Field(min_length=2, max_length=1200)


class ProposalConfirmRequest(BaseModel):
    action: Literal["DRAFT", "PUBLISH"]


class AgentConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_channel: str
    actor_role: str
    external_conversation_id: str
    title: str
    status: str
    messages: list[dict[str, Any]] = Field(default_factory=list)
    last_execution: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class ProductProposalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    hotel_id: int
    conversation_id: int | None
    product_id: int
    source_channel: str
    status: str
    trace_ids: list[str] = Field(default_factory=list)
    insight_snapshot: dict[str, Any] | None = None
    weather_snapshot: dict[str, Any] | None = None
    knowledge_snapshot: list[dict[str, Any]] = Field(default_factory=list)
    execution_steps: list[dict[str, Any]] = Field(default_factory=list)
    confirmation_action: str = ""
    confirmed_by: str = ""
    confirmed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    product: ProductRead | None = None


class AssistantTaskResponse(BaseModel):
    conversation: AgentConversationRead
    proposals: list[ProductProposalRead]
    message: str
