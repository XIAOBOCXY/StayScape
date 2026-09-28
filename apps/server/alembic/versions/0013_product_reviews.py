"""Store traveller reviews per product instead of rendering a fixed score."""

from alembic import op
import sqlalchemy as sa


revision = "0013_product_reviews"
down_revision = "0012_product_party_size"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("travel_products.id"), nullable=False),
        sa.Column("author_name", sa.String(length=60), nullable=False),
        sa.Column("author_tag", sa.String(length=60), nullable=False, server_default=""),
        sa.Column("rating", sa.Numeric(3, 1), nullable=False, server_default="5.0"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("highlights", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("source", sa.String(length=60), nullable=False, server_default="平台订单点评"),
        sa.Column("stayed_on", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_product_reviews_product_id", "product_reviews", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_product_reviews_product_id", table_name="product_reviews")
    op.drop_table("product_reviews")
