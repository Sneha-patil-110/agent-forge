from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '8a676672128b'
down_revision: Union[str, Sequence[str], None] = '8a037aad2678'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('documentation_files',
    sa.Column('run_id', sa.String(length=32), nullable=False),
    sa.Column('path', sa.String(), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('description', sa.String(), nullable=True),
    sa.Column('generating_agent', sa.String(length=32), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['run_id'], ['runs.run_id'], ),
    sa.PrimaryKeyConstraint('run_id', 'path')
    )
    op.create_index(op.f('ix_documentation_files_run_id'), 'documentation_files', ['run_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_documentation_files_run_id'), table_name='documentation_files')
    op.drop_table('documentation_files')
