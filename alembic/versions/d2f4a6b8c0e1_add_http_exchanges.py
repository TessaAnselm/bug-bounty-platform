"""add http_exchanges table

Revision ID: d2f4a6b8c0e1
Revises: a4f2e9c3b1d8
Create Date: 2026-06-10

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = 'd2f4a6b8c0e1'
down_revision = 'a4f2e9c3b1d8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'http_exchanges',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('hunt_session_id', UUID(as_uuid=True), sa.ForeignKey('hunt_sessions.id'), nullable=True),
        sa.Column('program_id', UUID(as_uuid=True), sa.ForeignKey('programs.id'), nullable=False),
        sa.Column('asset_id', UUID(as_uuid=True), sa.ForeignKey('assets.id'), nullable=True),
        sa.Column('finding_id', UUID(as_uuid=True), sa.ForeignKey('findings.id'), nullable=True),
        sa.Column('is_evidence', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('request_method', sa.Text(), nullable=False),
        sa.Column('request_url', sa.Text(), nullable=False),
        sa.Column('request_headers', JSONB(), nullable=False, server_default='{}'),
        sa.Column('request_body', sa.Text(), nullable=True),
        sa.Column('response_status', sa.Integer(), nullable=True),
        sa.Column('response_headers', JSONB(), nullable=True),
        sa.Column('response_body', sa.Text(), nullable=True),
        sa.Column('response_time_ms', sa.Integer(), nullable=True),
        sa.Column('label', sa.Text(), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_http_exchanges_hunt_session_id', 'http_exchanges', ['hunt_session_id'])
    op.create_index('ix_http_exchanges_program_id', 'http_exchanges', ['program_id'])
    op.create_index('ix_http_exchanges_finding_id', 'http_exchanges', ['finding_id'])


def downgrade() -> None:
    op.drop_index('ix_http_exchanges_finding_id', table_name='http_exchanges')
    op.drop_index('ix_http_exchanges_hunt_session_id', table_name='http_exchanges')
    op.drop_index('ix_http_exchanges_program_id', table_name='http_exchanges')
    op.drop_table('http_exchanges')
