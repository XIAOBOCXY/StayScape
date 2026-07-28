"""Persist the weather context used when a product was generated."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0002_product_weather"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("travel_products")}
    if "weather" not in columns:
        op.add_column("travel_products", sa.Column("weather", sa.String(length=20), nullable=False, server_default="RAIN"))


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("travel_products")}
    if "weather" in columns:
        op.drop_column("travel_products", "weather")

