from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'd19a5e6f0c3b'
down_revision: Union[str, Sequence[str], None] = 'c4d8f21a9b6e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES = "completed_with_verification_issues"
    # is 35 characters, longer than the VARCHAR(32) these columns were created with. Any run
    # that ends in that status fails to sync to Postgres (StringDataRightTruncation), leaving
    # its dashboard status frozen at whatever last synced successfully.
    op.alter_column('runs', 'status', type_=sa.String(length=64))
    op.alter_column('projects', 'status', type_=sa.String(length=64))


def downgrade() -> None:
    op.alter_column('projects', 'status', type_=sa.String(length=32))
    op.alter_column('runs', 'status', type_=sa.String(length=32))
