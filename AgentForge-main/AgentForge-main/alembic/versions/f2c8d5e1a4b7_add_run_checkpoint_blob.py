from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'f2c8d5e1a4b7'
down_revision: Union[str, Sequence[str], None] = 'e7b4a1f9c2d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('runs', sa.Column('checkpoint_blob', sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    op.drop_column('runs', 'checkpoint_blob')
