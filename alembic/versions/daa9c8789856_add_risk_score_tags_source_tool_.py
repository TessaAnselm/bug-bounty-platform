"""add risk_score tags source_tool interesting to assets

Revision ID: daa9c8789856
Revises: 57154eda7e38
Create Date: 2026-05-25 16:08:33.278184

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'daa9c8789856'
down_revision: Union[str, None] = '57154eda7e38'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("assets", sa.Column("risk_score", sa.Integer(), nullable=True))
    op.add_column("assets", sa.Column("tags", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"))
    op.add_column("assets", sa.Column("source_tool", sa.String(), nullable=True))
    op.add_column("assets", sa.Column("interesting", sa.Boolean(), nullable=False, server_default="false"))


def downgrade() -> None:
    op.drop_column("assets", "interesting")
    op.drop_column("assets", "source_tool")
    op.drop_column("assets", "tags")
    op.drop_column("assets", "risk_score")
