"""Store generated multi-channel marketing materials on travel products."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0003_product_marketing_assets"
down_revision = "0002_product_weather"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("travel_products")}
    if "marketing_assets" not in columns:
        op.add_column("travel_products", sa.Column("marketing_assets", sa.JSON(), nullable=True))


def downgrade() -> None:
    inspector = inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("travel_products")}
    if "marketing_assets" in columns:
        op.drop_column("travel_products", "marketing_assets")
