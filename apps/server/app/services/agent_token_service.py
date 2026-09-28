"""Hash-only bounded tokens for external ClawHive/Agent connections."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.exceptions import AppError
from ..models import AgentApiToken, User


TOKEN_PREFIX = "stsc_live_"


def token_digest(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_token(db: Session, *, user: User, hotel_id: int, name: str) -> tuple[AgentApiToken, str]:
    clean_name = " ".join(str(name or "").split()).strip()
    if not clean_name or len(clean_name) > 120:
        raise AppError("VALIDATION_ERROR", "Token 名称不能为空且不能超过 120 个字符", field="name", status_code=422)
    raw = TOKEN_PREFIX + secrets.token_urlsafe(32)
    row = AgentApiToken(
        user_id=user.id,
        hotel_id=hotel_id,
        name=clean_name,
        token_hash=token_digest(raw),
        is_active=True,
    )
    db.add(row)
    db.flush()
    return row, raw


def list_tokens(db: Session, *, user: User, hotel_id: int) -> list[AgentApiToken]:
    return list(
        db.scalars(
            select(AgentApiToken)
            .where(AgentApiToken.user_id == user.id, AgentApiToken.hotel_id == hotel_id)
            .order_by(AgentApiToken.created_at.desc(), AgentApiToken.id.desc())
        ).all()
    )


def revoke_token(db: Session, *, user: User, hotel_id: int, token_id: int) -> AgentApiToken:
    row = db.scalar(
        select(AgentApiToken).where(
            AgentApiToken.id == token_id,
            AgentApiToken.user_id == user.id,
            AgentApiToken.hotel_id == hotel_id,
        )
    )
    if row is None:
        raise AppError("NOT_FOUND", "Agent Token 不存在", status_code=404)
    row.is_active = False
    return row


def resolve_read_token(db: Session, raw_token: str | None) -> AgentApiToken:
    if not raw_token or not raw_token.startswith(TOKEN_PREFIX):
        raise AppError("AGENT_TOKEN_INVALID", "Agent Token 无效或已撤销", status_code=401)
    row = db.scalar(
        select(AgentApiToken).where(
            AgentApiToken.token_hash == token_digest(raw_token),
            AgentApiToken.is_active.is_(True),
        )
    )
    if row is None:
        raise AppError("AGENT_TOKEN_INVALID", "Agent Token 无效或已撤销", status_code=401)
    row.last_used_at = datetime.now(timezone.utc)
    return row
