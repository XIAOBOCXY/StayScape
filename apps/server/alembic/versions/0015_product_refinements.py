"""Track product versions and the conversational refinement history."""

from alembic import op
import sqlalchemy as sa


revision = "0015_product_refinements"
down_revision = "0014_product_nights"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "travel_products",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.alter_column("travel_products", "version", server_default=None)
    # 体验层调整（例如「第一天下午别排这么满」）落在 JSON 覆盖上，不动库存与成本。
    op.add_column(
        "travel_products",
        sa.Column("experience_notes", sa.JSON(), nullable=True),
    )
    op.create_table(
        "product_refinements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("hotel_id", sa.Integer(), nullable=False, index=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("travel_products.id"), nullable=False, index=True),
        sa.Column("conversation_id", sa.Integer(), nullable=True),
        sa.Column("layer", sa.String(30), nullable=False),
        sa.Column("instruction", sa.Text(), nullable=False, server_default=""),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("changes", sa.JSON(), nullable=True),
        sa.Column("checks", sa.JSON(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("product_refinements")
    op.drop_column("travel_products", "experience_notes")
    op.drop_column("travel_products", "version")
