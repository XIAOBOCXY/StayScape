"""Persist visitor confirmation data and Agent provider observability."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0006_visitor_agent_observability"
down_revision = "0005_catalog_richness"
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
    _add("visitor_intents", sa.Column("natural_language", sa.Text(), nullable=False, server_default=""))
    _add("visitor_intents", sa.Column("negative_interests", sa.JSON(), nullable=False, server_default="[]"))
    _add("visitor_intents", sa.Column("activity_level", sa.String(20), nullable=False, server_default="MEDIUM"))
    _add("skill_call_logs", sa.Column("provider", sa.String(20), nullable=False, server_default="MOCK"))
    _add("skill_call_logs", sa.Column("transport", sa.String(40), nullable=False, server_default="mock"))
    _add("skill_call_logs", sa.Column("agent_id", sa.String(160), nullable=False, server_default=""))
    _add("skill_call_logs", sa.Column("model", sa.String(160), nullable=False, server_default=""))
    _add("skill_call_logs", sa.Column("skill_version", sa.String(40), nullable=False, server_default=""))
    _add("skill_call_logs", sa.Column("fallback_used", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    for name in ("fallback_used", "skill_version", "model", "agent_id", "transport", "provider"):
        _drop("skill_call_logs", name)
    for name in ("activity_level", "negative_interests", "natural_language"):
        _drop("visitor_intents", name)
