from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c4d8f21a9b6e'
down_revision: Union[str, Sequence[str], None] = 'f3a9c1d7b2e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('runs', sa.Column('state_json', sa.Text(), nullable=True))
    op.add_column('runs', sa.Column('run_metadata_json', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('runs', 'run_metadata_json')
    op.drop_column('runs', 'state_json')
