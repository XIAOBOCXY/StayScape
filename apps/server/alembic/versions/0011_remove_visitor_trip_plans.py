"""Remove retired visitor multi-day self-package storage.

The visitor product journey now works only from hotel-confirmed, published
products.  Removing this table prevents a retired self-package hold from being
mistaken for an active booking path.
"""

from alembic import op
import sqlalchemy as sa


revision = "0011_remove_visitor_trip_plans"
down_revision = "0010_hotel_ai_operations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("visitor_trip_plans")


def downgrade() -> None:
    op.create_table(
        "visitor_trip_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("hotel_id", sa.Integer(), sa.ForeignKey("hotels.id"), nullable=False),
        sa.Column("source_product_id", sa.Integer(), sa.ForeignKey("travel_products.id"), nullable=True),
        sa.Column("plan_name", sa.String(length=180), nullable=False, server_default="杭州自定义行程"),
        sa.Column("natural_language", sa.Text(), nullable=False, server_default=""),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("target_crowd", sa.String(length=60), nullable=False, server_default="FRIENDS"),
        sa.Column("party_size", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("itinerary", sa.JSON(), nullable=True),
        sa.Column("total_price", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="DRAFT"),
        sa.Column("reserved_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("allocation_snapshot", sa.JSON(), nullable=True),
        sa.Column("contact_name", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("contact_phone", sa.String(length=40), nullable=False, server_default=""),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
