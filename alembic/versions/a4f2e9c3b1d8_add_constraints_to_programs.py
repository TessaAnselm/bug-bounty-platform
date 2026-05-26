"""add constraints to programs

Revision ID: a4f2e9c3b1d8
Revises: 651e8677fdfc
Create Date: 2026-05-26

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'a4f2e9c3b1d8'
down_revision = '651e8677fdfc'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('programs', sa.Column('constraints', JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column('programs', 'constraints')
