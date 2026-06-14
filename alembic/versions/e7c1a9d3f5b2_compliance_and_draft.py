"""add draft program status, program compliance checklist, ensure evidence cols

Revision ID: e7c1a9d3f5b2
Revises: d2f4a6b8c0e1
Create Date: 2026-06-14

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'e7c1a9d3f5b2'
down_revision = 'd2f4a6b8c0e1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # New 'draft' lifecycle state: a program stays here until the compliance
    # checklist is complete and it is explicitly activated. (PostgreSQL 12+
    # allows ADD VALUE inside a transaction as long as it isn't used here.)
    op.execute("ALTER TYPE programstatus ADD VALUE IF NOT EXISTS 'draft'")

    # Per-program compliance checklist attestations (terms accepted, OOS reviewed,
    # rate limit confirmed, active-scanning decision, prohibited tools).
    op.add_column('programs', sa.Column('compliance', JSONB(), nullable=True))

    # Defensive: finding_id / is_evidence were appended to the http_exchanges
    # migration after it may already have been applied, so the columns could be
    # missing in some databases. Ensure they exist regardless of when that ran.
    op.execute("ALTER TABLE http_exchanges ADD COLUMN IF NOT EXISTS finding_id UUID REFERENCES findings(id)")
    op.execute("ALTER TABLE http_exchanges ADD COLUMN IF NOT EXISTS is_evidence BOOLEAN NOT NULL DEFAULT false")
    op.execute("CREATE INDEX IF NOT EXISTS ix_http_exchanges_finding_id ON http_exchanges (finding_id)")


def downgrade() -> None:
    op.drop_column('programs', 'compliance')
    # The 'draft' enum value is left in place — PostgreSQL cannot drop an enum
    # value. The evidence columns are owned by the http_exchanges migration and
    # are intentionally not dropped here.
