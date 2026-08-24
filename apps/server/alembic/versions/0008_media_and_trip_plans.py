"""Add resource media metadata and held visitor multi-day trip plans."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0008_media_and_trip_plans"
down_revision = "0007_request_context_logs"
branch_labels = None
depends_on = None


def _add(table: str, column: sa.Column) -> None:
    columns = {item["name"] for item in inspect(op.get_bind()).get_columns(table)}
    if column.name not in columns:
        op.add_column(table, column)


def upgrade() -> None:
    for table in ("room_inventories", "hotel_services", "partner_resources"):
        _add(table, sa.Column("image_url", sa.String(length=500), nullable=False, server_default=""))
        _add(table, sa.Column("image_source", sa.String(length=120), nullable=False, server_default=""))
        _add(table, sa.Column("image_attribution", sa.String(length=500), nullable=False, server_default=""))

    bind = op.get_bind()
    if not inspect(bind).has_table("visitor_trip_plans"):
        op.create_table(
            "visitor_trip_plans",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("hotel_id", sa.Integer(), sa.ForeignKey("hotels.id"), nullable=False, index=True),
            sa.Column("source_product_id", sa.Integer(), sa.ForeignKey("travel_products.id"), nullable=True, index=True),
            sa.Column("plan_name", sa.String(length=180), nullable=False, server_default="杭州自定义行程"),
            sa.Column("natural_language", sa.Text(), nullable=False, server_default=""),
            sa.Column("start_date", sa.Date(), nullable=False, index=True),
            sa.Column("duration_days", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("target_crowd", sa.String(length=60), nullable=False, server_default="FRIENDS"),
            sa.Column("party_size", sa.Integer(), nullable=False, server_default="2"),
            sa.Column("itinerary", sa.JSON(), nullable=True),
            sa.Column("total_price", sa.Numeric(12, 2), nullable=False, server_default="0"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="DRAFT"),
            sa.Column("reserved_until", sa.DateTime(timezone=True), nullable=True),
            sa.Column("allocation_snapshot", sa.JSON(), nullable=True),
            sa.Column("contact_name", sa.String(length=80), nullable=False, server_default=""),
            sa.Column("contact_phone", sa.String(length=40), nullable=False, server_default=""),
            sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if inspect(bind).has_table("visitor_trip_plans"):
        op.drop_table("visitor_trip_plans")
    for table in ("partner_resources", "hotel_services", "room_inventories"):
        columns = {item["name"] for item in inspect(bind).get_columns(table)}
        for column in ("image_attribution", "image_source", "image_url"):
            if column in columns:
                op.drop_column(table, column)
