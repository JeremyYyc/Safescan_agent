"""Durable report work queue; LangGraph checkpoint data is managed by its saver."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '20260902_0003'
down_revision = '20260831_0002'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('report_jobs',
        sa.Column('job_id', sa.Text(), primary_key=True),
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.user_id', ondelete='CASCADE'), nullable=False),
        sa.Column('chat_id', sa.BigInteger(), sa.ForeignKey('chats.id', ondelete='CASCADE'), nullable=False),
        sa.Column('video_asset_id', sa.Text(), nullable=False),
        sa.Column('attributes', postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('status', sa.Text(), nullable=False, server_default='queued'),
        sa.Column('attempt', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('locked_by', sa.Text()), sa.Column('lease_expires_at', sa.DateTime(timezone=True)),
        sa.Column('error', sa.Text()), sa.Column('result', postgresql.JSONB()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.CheckConstraint("status IN ('queued','running','succeeded','failed','cancelled')", name='report_jobs_status_valid'))
    op.create_index('ix_report_jobs_claim', 'report_jobs', ['status', 'created_at'])
    op.create_index('uq_report_jobs_one_active_chat', 'report_jobs', ['chat_id'], unique=True, postgresql_where=sa.text("status IN ('queued','running')"))
    op.create_table('report_job_events',
        sa.Column('sequence', sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column('job_id', sa.Text(), sa.ForeignKey('report_jobs.job_id', ondelete='CASCADE'), nullable=False),
        sa.Column('event', postgresql.JSONB(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')))
    op.create_index('ix_report_job_events_job_sequence', 'report_job_events', ['job_id', 'sequence'])

def downgrade():
    op.drop_table('report_job_events')
    op.drop_table('report_jobs')
