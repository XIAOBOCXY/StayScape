"""Add an idempotency key to visitor intents.

A visitor submission that is retried (double tap, flaky network, client retry)
must not reserve a second room and a second experience slot.  The client sends
``client_request_id``; the partial unique index makes the key unique only when
it is actually supplied, so historical rows with an empty value are untouched.
"""

from alembic import op
import sqlalchemy as sa


revision = "0017_visitor_intent_idempotency"
down_revision = "0016_agent_api_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "visitor_intents",
        sa.Column("client_request_id", sa.String(length=120), nullable=False, server_default=""),
    )
    op.create_index("ix_visitor_intents_client_request_id", "visitor_intents", ["client_request_id"])
    op.create_index(
        "uq_visitor_intents_product_client_request",
        "visitor_intents",
        ["product_id", "client_request_id"],
        unique=True,
        postgresql_where=sa.text("client_request_id <> ''"),
        sqlite_where=sa.text("client_request_id <> ''"),
    )


def downgrade() -> None:
    op.drop_index("uq_visitor_intents_product_client_request", table_name="visitor_intents")
    op.drop_index("ix_visitor_intents_client_request_id", table_name="visitor_intents")
    op.drop_column("visitor_intents", "client_request_id")
