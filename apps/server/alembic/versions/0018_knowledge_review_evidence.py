"""Store source reachability separately from human fact review."""
from alembic import op
import sqlalchemy as sa

revision = "0018_knowledge_review_evidence"
down_revision = "0017_visitor_intent_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("travel_knowledge", sa.Column("source_checked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("travel_knowledge", sa.Column("source_reachable", sa.Boolean(), nullable=True))
    op.add_column("travel_knowledge", sa.Column("verified_by_user_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_travel_knowledge_verified_by_user_id", "travel_knowledge", "users", ["verified_by_user_id"], ["id"])
    op.add_column("travel_knowledge", sa.Column("verification_note", sa.Text(), nullable=False, server_default=""))
    op.add_column("travel_knowledge", sa.Column("verified_fields", sa.JSON(), nullable=False, server_default="[]"))
    op.execute("UPDATE travel_knowledge SET verification_status='VERIFY_REQUIRED', verified_at=NULL, source_updated_at=NULL, verified_fields='[]'")


def downgrade() -> None:
    op.drop_column("travel_knowledge", "verified_fields")
    op.drop_column("travel_knowledge", "verification_note")
    op.drop_constraint("fk_travel_knowledge_verified_by_user_id", "travel_knowledge", type_="foreignkey")
    op.drop_column("travel_knowledge", "verified_by_user_id")
    op.drop_column("travel_knowledge", "source_reachable")
    op.drop_column("travel_knowledge", "source_checked_at")
