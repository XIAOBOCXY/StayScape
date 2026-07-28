from typing import Any

from pydantic import BaseModel, ConfigDict


class ErrorBody(BaseModel):
    code: str
    message: str
    field: str | None = None
    retryable: bool = False
    suggestion: str | None = None
    details: Any = None


class ErrorResponse(BaseModel):
    success: bool = False
    error: ErrorBody


class MessageResponse(BaseModel):
    success: bool = True
    message: str


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

