"""Persist tenant ownership, pricing policy and visitor inventory holds."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0004_operational_consistency"
down_revision = "0003_product_marketing_assets"
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
    # Keep the column addition portable to SQLite; the ORM model still enforces
    # the relationship and PostgreSQL deployments can add the FK separately.
    _add("users", sa.Column("hotel_id", sa.Integer(), nullable=True))
    _add(
        "travel_products",
        sa.Column("minimum_gross_margin_requirement", sa.Numeric(10, 6), nullable=False, server_default="0.20"),
    )
    _add("travel_products", sa.Column("visitor_budget_limit", sa.Numeric(12, 2), nullable=False, server_default="700"))
    _add("travel_products", sa.Column("price_anchor", sa.Numeric(12, 2), nullable=False, server_default="599"))
    _add("visitor_intents", sa.Column("reservation_status", sa.String(20), nullable=False, server_default="CONFIRMED"))
    _add("visitor_intents", sa.Column("reserved_until", sa.DateTime(timezone=True), nullable=True))
    _add("visitor_intents", sa.Column("allocation_snapshot", sa.JSON(), nullable=True))
    _add("visitor_intents", sa.Column("released_at", sa.DateTime(timezone=True), nullable=True))
    _add("visitor_intents", sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True))
    _add("resource_change_events", sa.Column("hotel_id", sa.Integer(), nullable=True))
    _add("skill_call_logs", sa.Column("hotel_id", sa.Integer(), nullable=True))

    # Existing demo rows belong to the first hotel.  New writes always carry an
    # explicit tenant id, but this backfill keeps an upgraded local database usable.
    op.execute("UPDATE users SET hotel_id = (SELECT MIN(id) FROM hotels) WHERE role = 'HOTEL' AND hotel_id IS NULL")
    op.execute("UPDATE resource_change_events SET hotel_id = (SELECT hotel_id FROM room_inventories WHERE room_inventories.id = resource_change_events.resource_id) WHERE resource_type = 'ROOM' AND hotel_id IS NULL")
    op.execute("UPDATE resource_change_events SET hotel_id = (SELECT hotel_id FROM hotel_services WHERE hotel_services.id = resource_change_events.resource_id) WHERE resource_type = 'HOTEL_SERVICE' AND hotel_id IS NULL")
    op.execute("UPDATE resource_change_events SET hotel_id = (SELECT merchants.hotel_id FROM partner_resources JOIN merchants ON merchants.id = partner_resources.merchant_id WHERE partner_resources.id = resource_change_events.resource_id) WHERE resource_type = 'PARTNER_RESOURCE' AND hotel_id IS NULL")

    inspector = inspect(op.get_bind())
    indexes = {item["name"] for item in inspector.get_indexes("users")}
    if "ix_users_hotel_id" not in indexes:
        op.create_index("ix_users_hotel_id", "users", ["hotel_id"], unique=False)
    indexes = {item["name"] for item in inspector.get_indexes("resource_change_events")}
    if "ix_resource_change_events_hotel_id" not in indexes:
        op.create_index("ix_resource_change_events_hotel_id", "resource_change_events", ["hotel_id"], unique=False)
    indexes = {item["name"] for item in inspector.get_indexes("skill_call_logs")}
    if "ix_skill_call_logs_hotel_id" not in indexes:
        op.create_index("ix_skill_call_logs_hotel_id", "skill_call_logs", ["hotel_id"], unique=False)


def downgrade() -> None:
    for index_name, table in (
        ("ix_skill_call_logs_hotel_id", "skill_call_logs"),
        ("ix_resource_change_events_hotel_id", "resource_change_events"),
        ("ix_users_hotel_id", "users"),
    ):
        indexes = {item["name"] for item in inspect(op.get_bind()).get_indexes(table)}
        if index_name in indexes:
            op.drop_index(index_name, table_name=table)
    for table, name in (
        ("skill_call_logs", "hotel_id"),
        ("resource_change_events", "hotel_id"),
        ("visitor_intents", "confirmed_at"),
        ("visitor_intents", "released_at"),
        ("visitor_intents", "allocation_snapshot"),
        ("visitor_intents", "reserved_until"),
        ("visitor_intents", "reservation_status"),
        ("travel_products", "price_anchor"),
        ("travel_products", "visitor_budget_limit"),
        ("travel_products", "minimum_gross_margin_requirement"),
        ("users", "hotel_id"),
    ):
        _drop(table, name)
