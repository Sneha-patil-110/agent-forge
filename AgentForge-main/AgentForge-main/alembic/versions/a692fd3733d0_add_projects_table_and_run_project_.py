from datetime import UTC, datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a692fd3733d0'
down_revision: Union[str, Sequence[str], None] = '8a676672128b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:

    op.rename_table('projects', 'generated_projects')

    op.create_table(
        'projects',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=True),
        sa.Column('initial_prompt', sa.String(), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('run_count', sa.Integer(), nullable=False),
        sa.Column('latest_run_id', sa.String(length=32), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_projects_user_id'), 'projects', ['user_id'], unique=False)

    op.add_column('runs', sa.Column('project_id', sa.String(length=32), nullable=True))
    op.add_column('runs', sa.Column('request_text', sa.String(), nullable=True))
    op.create_index(op.f('ix_runs_project_id'), 'runs', ['project_id'], unique=False)
    op.create_foreign_key(
        'fk_runs_project_id_projects', 'runs', 'projects', ['project_id'], ['id']
    )
    op.create_foreign_key(
        'fk_projects_latest_run_id_runs', 'projects', 'runs', ['latest_run_id'], ['run_id']
    )

    _backfill_legacy_projects()


def downgrade() -> None:

    op.drop_constraint('fk_projects_latest_run_id_runs', 'projects', type_='foreignkey')
    op.drop_constraint('fk_runs_project_id_projects', 'runs', type_='foreignkey')
    op.drop_index(op.f('ix_runs_project_id'), table_name='runs')
    op.drop_column('runs', 'request_text')
    op.drop_column('runs', 'project_id')
    op.drop_table('projects')
    op.rename_table('generated_projects', 'projects')


def _backfill_legacy_projects() -> None:

    from backend.services.run_service import RunService
    from backend.utils.project_id import generate_project_id

    bind = op.get_bind()
    run_service = RunService()

    runs = bind.execute(
        sa.text("SELECT run_id, user_id, status, created_at, updated_at FROM runs ORDER BY created_at")
    ).fetchall()

    for run in runs:
        name = run.run_id

        try:
            state = run_service.load_state(run.run_id)

            if state.conversation.messages:
                content = state.conversation.messages[0].content

                if isinstance(content, str) and content.strip():
                    name = content.strip()[:120]
        except Exception as error:
            print(f"Warning: could not load state for run {run.run_id!r} during project backfill: {error}")

        project_id = generate_project_id()
        now = datetime.now(UTC)

        bind.execute(
            sa.text(
                "INSERT INTO projects "
                "(id, user_id, name, initial_prompt, status, run_count, latest_run_id, created_at, updated_at) "
                "VALUES (:id, :user_id, :name, :initial_prompt, :status, 1, :run_id, :created_at, :updated_at)"
            ),
            {
                "id": project_id,
                "user_id": run.user_id,
                "name": name,
                "initial_prompt": name,
                "status": run.status,
                "run_id": run.run_id,
                "created_at": run.created_at or now,
                "updated_at": run.updated_at or now,
            },
        )
        bind.execute(
            sa.text("UPDATE runs SET project_id = :project_id, request_text = :name WHERE run_id = :run_id"),
            {"project_id": project_id, "name": name, "run_id": run.run_id},
        )
