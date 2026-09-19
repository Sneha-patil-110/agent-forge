from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e7b4a1f9c2d6'
down_revision: Union[str, Sequence[str], None] = 'd19a5e6f0c3b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('agent_invocations', 'repair_trigger', type_=sa.String(length=64))
    op.alter_column('agent_invocations', 'failure_category', type_=sa.String(length=64))


def downgrade() -> None:
    op.alter_column('agent_invocations', 'failure_category', type_=sa.String(length=32))
    op.alter_column('agent_invocations', 'repair_trigger', type_=sa.String(length=32))
