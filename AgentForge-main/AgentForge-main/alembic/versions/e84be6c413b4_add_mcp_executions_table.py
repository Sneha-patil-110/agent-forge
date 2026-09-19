from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e84be6c413b4'
down_revision: Union[str, Sequence[str], None] = 'ac71fe1dae50'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('mcp_executions',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('run_id', sa.String(length=32), nullable=False),
    sa.Column('agent', sa.String(length=32), nullable=False),
    sa.Column('server_name', sa.String(length=64), nullable=False),
    sa.Column('tool_name', sa.String(length=128), nullable=False),
    sa.Column('success', sa.Boolean(), nullable=False),
    sa.Column('duration_ms', sa.Float(), nullable=True),
    sa.Column('error_message', sa.String(), nullable=True),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['run_id'], ['runs.run_id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_mcp_executions_agent', 'mcp_executions', ['agent'], unique=False)
    op.create_index(op.f('ix_mcp_executions_run_id'), 'mcp_executions', ['run_id'], unique=False)
    op.create_index('ix_mcp_executions_server_success', 'mcp_executions', ['server_name', 'success'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_mcp_executions_server_success', table_name='mcp_executions')
    op.drop_index(op.f('ix_mcp_executions_run_id'), table_name='mcp_executions')
    op.drop_index('ix_mcp_executions_agent', table_name='mcp_executions')
    op.drop_table('mcp_executions')
