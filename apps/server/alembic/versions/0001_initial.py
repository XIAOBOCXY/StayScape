"""Create the StayScape competition schema."""

from alembic import op

from app.models import Base

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The declarative metadata is the single source of truth. Alembic still
    # owns the migration boundary, while create_all keeps this initial schema
    # readable and portable across SQLite and PostgreSQL.
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())

