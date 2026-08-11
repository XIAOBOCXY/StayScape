"""Persist entry-point and conversation isolation metadata for Skill calls."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0007_request_context_logs"
down_revision = "0006_visitor_agent_observability"
branch_labels = None
depends_on = None


def _add(table: str, column: sa.Column) -> None:
    columns = {item["name"] for item in inspect(op.get_bind()).get_columns(table)}
    if column.name not in columns:
        op.add_column(table, column)


def _drop(table: str, name: str) -> None:
    columns = {item["name"] for item in inspect(op.get_bind()).get_columns(table)}
    if name in columns:
        op.drop_column(table, name)


def upgrade() -> None:
    _add("skill_call_logs", sa.Column("source_channel", sa.String(30), nullable=False, server_default="SYSTEM"))
    _add("skill_call_logs", sa.Column("actor_role", sa.String(30), nullable=False, server_default="SYSTEM"))
    _add("skill_call_logs", sa.Column("conversation_id", sa.String(160), nullable=False, server_default=""))


def downgrade() -> None:
    for name in ("conversation_id", "actor_role", "source_channel"):
        _drop("skill_call_logs", name)
