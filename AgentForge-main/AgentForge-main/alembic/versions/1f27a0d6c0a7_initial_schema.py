from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '1f27a0d6c0a7'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('runs',
    sa.Column('run_id', sa.String(length=32), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('current_step', sa.String(length=255), nullable=True),
    sa.Column('current_agent', sa.String(length=32), nullable=True),
    sa.Column('error_message', sa.String(), nullable=True),
    sa.Column('test_retry_count', sa.Integer(), nullable=False),
    sa.Column('review_retry_count', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('run_id')
    )
    op.create_table('users',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('username', sa.String(length=64), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('hashed_password', sa.String(length=255), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
    op.create_table('knowledge_entries',
    sa.Column('run_id', sa.String(length=32), nullable=False),
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('category', sa.String(length=64), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('content', sa.String(), nullable=False),
    sa.Column('created_by', sa.String(length=64), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('source_id', sa.String(length=64), nullable=True),
    sa.Column('supersedes', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['run_id'], ['runs.run_id'], ),
    sa.PrimaryKeyConstraint('run_id', 'id')
    )
    op.create_index(op.f('ix_knowledge_entries_run_id'), 'knowledge_entries', ['run_id'], unique=False)
    op.create_table('projects',
    sa.Column('run_id', sa.String(length=32), nullable=False),
    sa.Column('project_name', sa.String(length=255), nullable=True),
    sa.Column('project_description', sa.String(), nullable=True),
    sa.Column('objective', sa.String(), nullable=True),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('backend_tech', sa.String(length=128), nullable=True),
    sa.Column('frontend_tech', sa.String(length=128), nullable=True),
    sa.Column('database_tech', sa.String(length=128), nullable=True),
    sa.Column('deployment_tech', sa.String(length=128), nullable=True),
    sa.Column('requirements', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('tech_stack', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('output_directory', sa.String(), nullable=True),
    sa.ForeignKeyConstraint(['run_id'], ['runs.run_id'], ),
    sa.PrimaryKeyConstraint('run_id')
    )
    op.create_table('workflow_events',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('run_id', sa.String(length=32), nullable=False),
    sa.Column('event_type', sa.String(length=64), nullable=False),
    sa.Column('agent', sa.String(length=32), nullable=True),
    sa.Column('message', sa.String(), nullable=True),
    sa.Column('event_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['run_id'], ['runs.run_id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_workflow_events_run_id'), 'workflow_events', ['run_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_workflow_events_run_id'), table_name='workflow_events')
    op.drop_table('workflow_events')
    op.drop_table('projects')
    op.drop_index(op.f('ix_knowledge_entries_run_id'), table_name='knowledge_entries')
    op.drop_table('knowledge_entries')
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
    op.drop_table('runs')
