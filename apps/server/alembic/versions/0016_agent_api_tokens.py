"""Add hash-only external Agent API tokens."""

from alembic import op
import sqlalchemy as sa


revision = "0016_agent_api_tokens"
down_revision = "0015_product_refinements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_api_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("hotel_id", sa.Integer(), sa.ForeignKey("hotels.id"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_agent_api_tokens_user_id", "agent_api_tokens", ["user_id"])
    op.create_index("ix_agent_api_tokens_hotel_id", "agent_api_tokens", ["hotel_id"])
    op.create_index("ix_agent_api_tokens_token_hash", "agent_api_tokens", ["token_hash"])


def downgrade() -> None:
    op.drop_index("ix_agent_api_tokens_token_hash", table_name="agent_api_tokens")
    op.drop_index("ix_agent_api_tokens_hotel_id", table_name="agent_api_tokens")
    op.drop_index("ix_agent_api_tokens_user_id", table_name="agent_api_tokens")
    op.drop_table("agent_api_tokens")
