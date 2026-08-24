"""Keep a stable merchant listing cap separate from live remaining stock."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0009_product_listing_quantity"
down_revision = "0008_media_and_trip_plans"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {item["name"] for item in inspect(bind).get_columns("travel_products")}
    if "listed_quantity" not in columns:
        op.add_column(
            "travel_products",
            sa.Column("listed_quantity", sa.Integer(), nullable=False, server_default="0"),
        )
    # Existing rows were created before the split.  Their current quantity is
    # the only safe initial merchant ceiling; no historical stock is inferred.
    op.execute(
        "UPDATE travel_products "
        "SET listed_quantity = sale_quantity "
        "WHERE listed_quantity IS NULL OR listed_quantity = 0"
    )


def downgrade() -> None:
    bind = op.get_bind()
    columns = {item["name"] for item in inspect(bind).get_columns("travel_products")}
    if "listed_quantity" in columns:
        op.drop_column("travel_products", "listed_quantity")
