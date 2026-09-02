"""Add auditable hotel AI tasks, pending proposals and reviewed travel knowledge."""

from alembic import op
import sqlalchemy as sa


revision = "0010_hotel_ai_operations"
down_revision = "0009_product_listing_quantity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "travel_knowledge",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("area", sa.String(length=100), nullable=False, server_default="杭州"),
        sa.Column("address", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("indoor_outdoor", sa.String(length=20), nullable=False, server_default="MIXED"),
        sa.Column("suitable_crowds", sa.String(length=160), nullable=False, server_default="ALL"),
        sa.Column("minimum_age", sa.Integer(), nullable=True),
        sa.Column("maximum_age", sa.Integer(), nullable=True),
        sa.Column("suggested_duration_minutes", sa.Integer(), nullable=True),
        sa.Column("opening_hours", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("weather_adaptations", sa.String(length=180), nullable=False, server_default="CLOUDY"),
        sa.Column("reservation_notice", sa.Text(), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_name", sa.String(length=160), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_status", sa.String(length=30), nullable=False, server_default="VERIFY_REQUIRED"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_travel_knowledge_slug", "travel_knowledge", ["slug"], unique=True)

    op.create_table(
        "weather_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("city", sa.String(length=60), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("scenario", sa.String(length=20), nullable=False, server_default="CLOUDY"),
        sa.Column("temperature_min", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("temperature_max", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("precipitation_probability", sa.Integer(), nullable=True),
        sa.Column("weather_code", sa.Integer(), nullable=True),
        sa.Column("advisory", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("source_name", sa.String(length=160), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_status", sa.String(length=30), nullable=False, server_default="VERIFY_REQUIRED"),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("city", "target_date", name="uq_weather_snapshots_city_date"),
    )
    op.create_index("ix_weather_snapshots_city", "weather_snapshots", ["city"])
    op.create_index("ix_weather_snapshots_target_date", "weather_snapshots", ["target_date"])

    op.create_table(
        "agent_conversations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("hotel_id", sa.Integer(), sa.ForeignKey("hotels.id"), nullable=False),
        sa.Column("source_channel", sa.String(length=30), nullable=False),
        sa.Column("actor_role", sa.String(length=30), nullable=False),
        sa.Column("external_conversation_id", sa.String(length=180), nullable=False, server_default=""),
        sa.Column("title", sa.String(length=220), nullable=False, server_default="酒店 AI 运营任务"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="ACTIVE"),
        sa.Column("messages", sa.JSON(), nullable=False),
        sa.Column("last_execution", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agent_conversations_hotel_id", "agent_conversations", ["hotel_id"])
    op.create_index("ix_agent_conversations_external_conversation_id", "agent_conversations", ["external_conversation_id"])

    op.create_table(
        "product_proposals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("hotel_id", sa.Integer(), sa.ForeignKey("hotels.id"), nullable=False),
        sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("agent_conversations.id"), nullable=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("travel_products.id"), nullable=False),
        sa.Column("source_channel", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="PENDING_CONFIRMATION"),
        sa.Column("trace_ids", sa.JSON(), nullable=False),
        sa.Column("insight_snapshot", sa.JSON(), nullable=True),
        sa.Column("weather_snapshot", sa.JSON(), nullable=True),
        sa.Column("knowledge_snapshot", sa.JSON(), nullable=False),
        sa.Column("execution_steps", sa.JSON(), nullable=False),
        sa.Column("confirmation_action", sa.String(length=30), nullable=False, server_default=""),
        sa.Column("confirmed_by", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("product_id", name="uq_product_proposals_product_id"),
    )
    op.create_index("ix_product_proposals_hotel_id", "product_proposals", ["hotel_id"])
    op.create_index("ix_product_proposals_conversation_id", "product_proposals", ["conversation_id"])
    op.create_index("ix_product_proposals_status", "product_proposals", ["status"])


def downgrade() -> None:
    op.drop_index("ix_product_proposals_status", table_name="product_proposals")
    op.drop_index("ix_product_proposals_conversation_id", table_name="product_proposals")
    op.drop_index("ix_product_proposals_hotel_id", table_name="product_proposals")
    op.drop_table("product_proposals")
    op.drop_index("ix_agent_conversations_external_conversation_id", table_name="agent_conversations")
    op.drop_index("ix_agent_conversations_hotel_id", table_name="agent_conversations")
    op.drop_table("agent_conversations")
    op.drop_index("ix_travel_knowledge_slug", table_name="travel_knowledge")
    op.drop_table("travel_knowledge")
    op.drop_index("ix_weather_snapshots_target_date", table_name="weather_snapshots")
    op.drop_index("ix_weather_snapshots_city", table_name="weather_snapshots")
    op.drop_table("weather_snapshots")
