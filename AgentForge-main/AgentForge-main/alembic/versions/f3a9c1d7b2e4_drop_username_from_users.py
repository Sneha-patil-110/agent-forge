from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'f3a9c1d7b2e4'
down_revision: Union[str, Sequence[str], None] = 'e84be6c413b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_column('users', 'username')


def downgrade() -> None:
    op.add_column('users', sa.Column('username', sa.String(length=64), nullable=True))
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
