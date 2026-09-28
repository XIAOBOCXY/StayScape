"""Store the length of stay on the product itself."""

from alembic import op
import sqlalchemy as sa


revision = "0014_product_nights"
down_revision = "0013_product_reviews"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "travel_products",
        sa.Column("nights", sa.Integer(), nullable=False, server_default="1"),
    )
    op.alter_column("travel_products", "nights", server_default=None)


def downgrade() -> None:
    op.drop_column("travel_products", "nights")
