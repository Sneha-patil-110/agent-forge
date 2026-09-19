from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'ac71fe1dae50'
down_revision: Union[str, Sequence[str], None] = 'a692fd3733d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:

    op.alter_column('knowledge_entries', 'source_id', type_=sa.String(length=255))
    op.alter_column('knowledge_entries', 'supersedes', type_=sa.String(length=255))

    op.alter_column('generated_projects', 'backend_tech', type_=sa.String(length=255))
    op.alter_column('generated_projects', 'frontend_tech', type_=sa.String(length=255))
    op.alter_column('generated_projects', 'database_tech', type_=sa.String(length=255))
    op.alter_column('generated_projects', 'deployment_tech', type_=sa.String(length=255))

    op.create_table(
        'agent_invocations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('run_id', sa.String(length=32), nullable=False),
        sa.Column('agent', sa.String(length=32), nullable=False),
        sa.Column('attempt_number', sa.Integer(), nullable=False),
        sa.Column('repair_trigger', sa.String(length=32), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('provider', sa.String(length=32), nullable=True),
        sa.Column('model', sa.String(length=64), nullable=True),
        sa.Column('provider_request_id', sa.String(length=128), nullable=True),
        sa.Column('input_tokens', sa.Integer(), nullable=True),
        sa.Column('output_tokens', sa.Integer(), nullable=True),
        sa.Column('prompt_characters', sa.Integer(), nullable=True),
        sa.Column('response_characters', sa.Integer(), nullable=True),
        sa.Column('exception_type', sa.String(length=255), nullable=True),
        sa.Column('failure_category', sa.String(length=32), nullable=True),
        sa.Column('recovery_reason', sa.String(length=32), nullable=True),
        sa.Column('error_message', sa.String(), nullable=True),
        sa.Column('stacktrace', sa.String(), nullable=True),
        sa.Column('checkpoint_id', sa.String(length=128), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['run_id'], ['runs.run_id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_agent_invocations_run_id'), 'agent_invocations', ['run_id'], unique=False
    )
    op.create_index(
        op.f('ix_agent_invocations_agent_status'),
        'agent_invocations',
        ['agent', 'status'],
        unique=False,
    )


def downgrade() -> None:

    op.drop_index(op.f('ix_agent_invocations_agent_status'), table_name='agent_invocations')
    op.drop_index(op.f('ix_agent_invocations_run_id'), table_name='agent_invocations')
    op.drop_table('agent_invocations')

    op.alter_column('generated_projects', 'deployment_tech', type_=sa.String(length=128))
    op.alter_column('generated_projects', 'database_tech', type_=sa.String(length=128))
    op.alter_column('generated_projects', 'frontend_tech', type_=sa.String(length=128))
    op.alter_column('generated_projects', 'backend_tech', type_=sa.String(length=128))

    op.alter_column('knowledge_entries', 'supersedes', type_=sa.String(length=64))
    op.alter_column('knowledge_entries', 'source_id', type_=sa.String(length=64))
