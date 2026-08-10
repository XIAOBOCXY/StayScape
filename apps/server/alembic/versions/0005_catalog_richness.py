"""Add structured room targeting and partner resource provenance."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0005_catalog_richness"
down_revision = "0004_operational_consistency"
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
    _add("room_inventories", sa.Column("suitable_crowds", sa.String(120), nullable=False, server_default="ALL"))
    _add("room_inventories", sa.Column("tags", sa.String(240), nullable=False, server_default=""))
    _add("partner_resources", sa.Column("source_type", sa.String(30), nullable=False, server_default="PARTNER"))

    # Keep upgraded databases useful without requiring an operator to edit old rows.
    op.execute("UPDATE room_inventories SET suitable_crowds = 'ALL' WHERE suitable_crowds IS NULL OR suitable_crowds = ''")
    op.execute("UPDATE room_inventories SET tags = features WHERE tags IS NULL OR tags = ''")
    op.execute("UPDATE partner_resources SET source_type = 'PARTNER' WHERE source_type IS NULL OR source_type = ''")


def downgrade() -> None:
    _drop("partner_resources", "source_type")
    _drop("room_inventories", "tags")
    _drop("room_inventories", "suitable_crowds")
