from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '8a037aad2678'
down_revision: Union[str, Sequence[str], None] = '1f27a0d6c0a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('file_versions',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('run_id', sa.String(length=32), nullable=False),
    sa.Column('path', sa.String(), nullable=False),
    sa.Column('content', sa.String(), nullable=False),
    sa.Column('source', sa.String(length=16), nullable=False),
    sa.Column('edited_by', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['run_id'], ['runs.run_id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_file_versions_path'), 'file_versions', ['path'], unique=False)
    op.create_index(op.f('ix_file_versions_run_id'), 'file_versions', ['run_id'], unique=False)
    op.add_column('runs', sa.Column('user_id', sa.UUID(), nullable=True))
    op.create_index(op.f('ix_runs_user_id'), 'runs', ['user_id'], unique=False)
    op.create_foreign_key('fk_runs_user_id_users', 'runs', 'users', ['user_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint('fk_runs_user_id_users', 'runs', type_='foreignkey')
    op.drop_index(op.f('ix_runs_user_id'), table_name='runs')
    op.drop_column('runs', 'user_id')
    op.drop_index(op.f('ix_file_versions_run_id'), table_name='file_versions')
    op.drop_index(op.f('ix_file_versions_path'), table_name='file_versions')
    op.drop_table('file_versions')
