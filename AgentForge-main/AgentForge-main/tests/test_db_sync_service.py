from __future__ import annotations

from pathlib import Path

import pytest

from backend.events.event_types import EventType, WorkflowEvent
from backend.repositories.documentation_repository import DocumentationRepository
from backend.repositories.event_repository import EventRepository
from backend.repositories.generated_project_repository import GeneratedProjectRepository
from backend.repositories.knowledge_repository import KnowledgeRepository
from backend.repositories.project_repository import ProjectRepository
from backend.repositories.run_repository import RunRepository
from backend.services.db_sync_service import DatabaseSyncService
from backend.services.run_service import RunService
from backend.state.documentation_state import DocumentationFile
from backend.state.execution_state import AgentType, WorkflowStatus
from backend.state.knowledge_state import KnowledgeCategory
from backend.state.project_state import ProjectStatus


@pytest.fixture
def run_service(tmp_path: Path) -> RunService:
    return RunService(runs_root=tmp_path / "runs")


def test_disabled_without_a_session_factory_is_a_safe_no_op(run_service: RunService) -> None:
    service = DatabaseSyncService(session_factory=None, run_service=run_service)
    assert service.enabled is False

    service.handle_event(WorkflowEvent(event_type=EventType.WORKFLOW_STARTED, run_id="af_20260717_deadbeef"))


def test_snapshot_event_syncs_run_project_and_knowledge(run_service: RunService, db_session_factory) -> None:
    metadata = run_service.create_run()
    state = run_service.load_state(metadata.run_id)
    state.project.project_name = "Expense Tracker"
    state.project.status = ProjectStatus.ANALYZED
    state.execution.workflow_status = WorkflowStatus.RUNNING
    state.execution.current_agent = AgentType.DEVELOPER
    run_service.save_state(metadata.run_id, state)

    from backend.services.knowledge_manager import KnowledgeManager

    KnowledgeManager().record(
        state,
        category=KnowledgeCategory.CODING_STANDARD,
        title="Use snake_case",
        content="Use snake_case for functions.",
        created_by="reviewer",
    )
    run_service.save_state(metadata.run_id, state)

    service = DatabaseSyncService(session_factory=db_session_factory, run_service=run_service)
    assert service.enabled is True

    service.handle_event(
        WorkflowEvent(event_type=EventType.AGENT_COMPLETED, run_id=metadata.run_id, agent=AgentType.DEVELOPER)
    )

    with db_session_factory() as session:
        run_record = RunRepository(session).get(metadata.run_id)
        assert run_record is not None
        assert run_record.status == WorkflowStatus.RUNNING.value

        project_record = GeneratedProjectRepository(session).get(metadata.run_id)
        assert project_record.project_name == "Expense Tracker"

        knowledge_records = KnowledgeRepository(session).list_for_run(metadata.run_id)
        assert len(knowledge_records) == 1
        assert knowledge_records[0].title == "Use snake_case"


def test_snapshot_event_attaches_the_run_and_refreshes_the_grouping_projects_status(
    run_service: RunService, db_session_factory
) -> None:
    project_id = "proj_20260719_dbsync01"

    with db_session_factory() as session:
        ProjectRepository(session).create(
            id=project_id, user_id=None, name="Sync test", initial_prompt=None
        )
        session.commit()

    metadata = run_service.create_run(project_id=project_id)
    state = run_service.load_state(metadata.run_id)
    state.execution.workflow_status = WorkflowStatus.RUNNING
    run_service.save_state(metadata.run_id, state)

    service = DatabaseSyncService(session_factory=db_session_factory, run_service=run_service)
    service.handle_event(
        WorkflowEvent(event_type=EventType.AGENT_COMPLETED, run_id=metadata.run_id, agent=AgentType.DEVELOPER)
    )

    with db_session_factory() as session:
        run_record = RunRepository(session).get(metadata.run_id)
        assert run_record.project_id == project_id

        refreshed = ProjectRepository(session).get(project_id)
        assert refreshed.status == WorkflowStatus.RUNNING.value
        assert refreshed.latest_run_id == metadata.run_id
        assert refreshed.run_count == 1

    service.handle_event(
        WorkflowEvent(event_type=EventType.TESTING_PASSED, run_id=metadata.run_id, agent=AgentType.TESTER)
    )

    with db_session_factory() as session:
        assert ProjectRepository(session).get(project_id).run_count == 1


def test_non_snapshot_event_still_records_the_raw_event_row(run_service: RunService, db_session_factory) -> None:
    metadata = run_service.create_run()

    service = DatabaseSyncService(session_factory=db_session_factory, run_service=run_service)

    service.handle_event(WorkflowEvent(event_type=EventType.WORKFLOW_STARTED, run_id=metadata.run_id))

    service.handle_event(
        WorkflowEvent(
            event_type=EventType.MCP_TOOL_CALL_STARTED,
            run_id=metadata.run_id,
            agent=AgentType.DOCUMENTATION,
            metadata={"tool": "documentation.search_docs"},
        )
    )

    with db_session_factory() as session:
        events = EventRepository(session).list_for_run(metadata.run_id)
        event_types = [event.event_type for event in events]
        assert event_types == ["workflow_started", "mcp_tool_call_started"]


def test_documentation_generated_event_syncs_documentation_records(
    run_service: RunService, db_session_factory
) -> None:
    metadata = run_service.create_run()
    state = run_service.load_state(metadata.run_id)
    state.documentation.generated_docs = [
        DocumentationFile(title="Overview", path="README.md", content="# Overview\n"),
        DocumentationFile(
            title="API", path="docs/api.md", content="# API\n", description="Endpoint reference."
        ),
        DocumentationFile(title="Deployment", path="docs/deployment.md", content="# Deploy\n"),
    ]
    state.documentation.written_files = ["README.md", "docs/api.md"]
    state.documentation.file_write_errors = ["docs/deployment.md: disk full"]
    run_service.save_state(metadata.run_id, state)

    service = DatabaseSyncService(session_factory=db_session_factory, run_service=run_service)
    service.handle_event(WorkflowEvent(event_type=EventType.DOCUMENTATION_GENERATED, run_id=metadata.run_id))

    with db_session_factory() as session:
        records = {r.path: r for r in DocumentationRepository(session).list_for_run(metadata.run_id)}

    assert set(records) == {"README.md", "docs/api.md", "docs/deployment.md"}
    assert records["README.md"].status == "generated"
    assert records["README.md"].generating_agent == "documentation"
    assert records["docs/api.md"].description == "Endpoint reference."
    assert records["docs/deployment.md"].status == "failed"


def test_documentation_sync_is_a_no_op_before_materialization_has_run(
    run_service: RunService, db_session_factory
) -> None:
    metadata = run_service.create_run()
    state = run_service.load_state(metadata.run_id)
    state.documentation.generated_docs = [
        DocumentationFile(title="Overview", path="README.md", content="# Overview\n"),
    ]
    run_service.save_state(metadata.run_id, state)

    service = DatabaseSyncService(session_factory=db_session_factory, run_service=run_service)
    service.handle_event(WorkflowEvent(event_type=EventType.DOCUMENTATION_GENERATED, run_id=metadata.run_id))

    with db_session_factory() as session:
        records = DocumentationRepository(session).list_for_run(metadata.run_id)

    assert records == []


def test_a_database_failure_is_swallowed_not_raised(run_service: RunService) -> None:
    class _BrokenSessionFactory:
        def __call__(self):
            raise RuntimeError("connection refused")

    service = DatabaseSyncService(session_factory=_BrokenSessionFactory(), run_service=run_service)

    service.handle_event(WorkflowEvent(event_type=EventType.WORKFLOW_STARTED, run_id="af_20260717_deadbeef"))


def test_an_event_with_an_invalid_run_id_is_ignored_not_upserted(
    run_service: RunService, db_session_factory
) -> None:
    service = DatabaseSyncService(session_factory=db_session_factory, run_service=run_service)

    service.handle_event(
        WorkflowEvent(event_type=EventType.WORKFLOW_STARTED, run_id="proj_20260719_notarealrun")
    )

    with db_session_factory() as session:
        assert RunRepository(session).get("proj_20260719_notarealrun") is None