"""Persist the defined group size on each hotel product."""

from alembic import op
import sqlalchemy as sa


revision = "0012_product_party_size"
down_revision = "0011_remove_visitor_trip_plans"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "travel_products",
        sa.Column("party_size", sa.Integer(), nullable=False, server_default="2"),
    )
    op.alter_column("travel_products", "party_size", server_default=None)


def downgrade() -> None:
    op.drop_column("travel_products", "party_size")
