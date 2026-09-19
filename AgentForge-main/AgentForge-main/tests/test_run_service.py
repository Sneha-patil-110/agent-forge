from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from langchain_core.messages import HumanMessage

from backend.core.exceptions import InvalidRunIdError, RunCorruptedError, RunNotFoundError
from backend.services.run_service import RunService
from backend.state.documentation_state import DocumentationFile
from backend.state.execution_state import AgentType, RepairTrigger, WorkflowStatus
from backend.state.knowledge_state import KnowledgeCategory, KnowledgeEntry, KnowledgeStatus
from backend.state.testing_state import TestStatus
from backend.state.workflow_state import WorkflowState


@pytest.fixture
def run_service(tmp_path: Path) -> RunService:
    return RunService(runs_root=tmp_path / "runs")


def test_create_run_writes_metadata_and_state_files(run_service: RunService) -> None:
    metadata = run_service.create_run()
    run_dir = run_service.run_dir(metadata.run_id)

    assert (run_dir / "metadata.json").exists()
    assert (run_dir / "state.json").exists()


def test_create_run_initial_state_is_default_workflow_state(
    run_service: RunService,
) -> None:
    metadata = run_service.create_run()

    state = run_service.load_state(metadata.run_id)
    fresh = WorkflowState()

    exclude = {
        "execution": {"started_at"},
        "project": {"created_at", "updated_at"},
        "testing": {"timestamp"},
    }
    assert state.model_dump(exclude=exclude) == fresh.model_dump(exclude=exclude)


def test_run_exists_true_after_create_false_otherwise(run_service: RunService) -> None:
    metadata = run_service.create_run()

    assert run_service.run_exists(metadata.run_id) is True

    from backend.utils.run_id import generate_run_id

    assert run_service.run_exists(generate_run_id()) is False


def test_save_and_load_state_round_trips_full_workflow_state(
    run_service: RunService,
) -> None:
    metadata = run_service.create_run()

    state = WorkflowState()
    state.project.project_name = "Task Manager"
    state.execution.test_retry_count = 2
    state.execution.review_retry_count = 1
    state.testing.passed = True
    state.testing.command = ["python", "-m", "pytest"]

    run_service.save_state(metadata.run_id, state)
    reloaded = run_service.load_state(metadata.run_id)

    assert reloaded.project.project_name == "Task Manager"
    assert reloaded.execution.test_retry_count == 2
    assert reloaded.execution.review_retry_count == 1
    assert reloaded.testing.passed is True
    assert reloaded.testing.command == ["python", "-m", "pytest"]


def test_save_state_advances_metadata_updated_at(run_service: RunService) -> None:
    metadata = run_service.create_run()
    original_updated_at = metadata.updated_at

    run_service.save_state(metadata.run_id, WorkflowState())
    reloaded_metadata = run_service.load_metadata(metadata.run_id)

    assert reloaded_metadata.updated_at >= original_updated_at


def test_save_state_uses_atomic_write_no_temp_files_left(
    run_service: RunService,
) -> None:
    metadata = run_service.create_run()
    run_service.save_state(metadata.run_id, WorkflowState())

    run_dir = run_service.run_dir(metadata.run_id)
    entries = {p.name for p in run_dir.iterdir()}

    assert entries == {"metadata.json", "state.json"}


def test_load_state_missing_run_raises_run_not_found(run_service: RunService) -> None:
    from backend.utils.run_id import generate_run_id

    with pytest.raises(RunNotFoundError):
        run_service.load_state(generate_run_id())


def test_load_metadata_missing_run_raises_run_not_found(run_service: RunService) -> None:
    from backend.utils.run_id import generate_run_id

    with pytest.raises(RunNotFoundError):
        run_service.load_metadata(generate_run_id())


def test_load_state_retries_through_a_transient_permission_error(
    run_service: RunService, monkeypatch: pytest.MonkeyPatch
) -> None:
    metadata = run_service.create_run()

    real_read_text = Path.read_text
    calls = {"count": 0}

    def _flaky_read_text(self: Path, *args, **kwargs):
        if self.name == "state.json" and calls["count"] == 0:
            calls["count"] += 1
            raise PermissionError("simulated transient rename race")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _flaky_read_text)

    state = run_service.load_state(metadata.run_id)

    assert state is not None
    assert calls["count"] == 1


def test_load_state_gives_up_after_persistent_permission_errors(
    run_service: RunService, monkeypatch: pytest.MonkeyPatch
) -> None:
    metadata = run_service.create_run()
    real_read_text = Path.read_text

    def _always_denied(self: Path, *args, **kwargs):
        if self.name == "state.json":
            raise PermissionError("simulated persistent denial")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _always_denied)

    with pytest.raises(RunCorruptedError):
        run_service.load_state(metadata.run_id)


def test_save_state_missing_run_raises_run_not_found(run_service: RunService) -> None:
    from backend.utils.run_id import generate_run_id

    with pytest.raises(RunNotFoundError):
        run_service.save_state(generate_run_id(), WorkflowState())


def test_load_state_corrupted_json_raises_run_corrupted(
    run_service: RunService,
) -> None:
    metadata = run_service.create_run()
    run_dir = run_service.run_dir(metadata.run_id)
    (run_dir / "state.json").write_text("{not valid json", encoding="utf-8")

    with pytest.raises(RunCorruptedError):
        run_service.load_state(metadata.run_id)


def test_load_state_schema_mismatch_raises_run_corrupted(
    run_service: RunService,
) -> None:
    metadata = run_service.create_run()
    run_dir = run_service.run_dir(metadata.run_id)
    (run_dir / "state.json").write_text(
        '{"execution": {"test_retry_count": -1}}', encoding="utf-8"
    )

    with pytest.raises(RunCorruptedError):
        run_service.load_state(metadata.run_id)


def test_load_metadata_corrupted_json_raises_run_corrupted(
    run_service: RunService,
) -> None:
    metadata = run_service.create_run()
    run_dir = run_service.run_dir(metadata.run_id)
    (run_dir / "metadata.json").write_text("not json at all", encoding="utf-8")

    with pytest.raises(RunCorruptedError):
        run_service.load_metadata(metadata.run_id)


@pytest.mark.parametrize(
    "bad_run_id",
    [
        "../../secrets",
        "/etc/passwd",
        "af_test/../../../backend",
    ],
)
def test_run_dir_rejects_path_traversal(
    run_service: RunService, bad_run_id: str
) -> None:
    with pytest.raises(InvalidRunIdError):
        run_service.run_dir(bad_run_id)


def test_create_run_allocates_distinct_directories(run_service: RunService) -> None:
    first = run_service.create_run()
    second = run_service.create_run()

    assert first.run_id != second.run_id
    assert run_service.run_dir(first.run_id) != run_service.run_dir(second.run_id)


def test_create_run_persists_project_id_into_metadata(run_service: RunService) -> None:
    metadata = run_service.create_run(project_id="proj_20260719_aaaaaaaa")
    assert metadata.project_id == "proj_20260719_aaaaaaaa"

    reloaded = run_service.load_metadata(metadata.run_id)
    assert reloaded.project_id == "proj_20260719_aaaaaaaa"


def _prior_state_with_full_history() -> WorkflowState:
    prior = WorkflowState()
    prior.conversation.messages = [HumanMessage(content="Build a fastapi expense tracker")]
    prior.conversation.summary = "Initial expense tracker build."
    prior.project.project_name = "Expense Tracker"
    prior.project.output_directory = "/workspace/proj_x"
    prior.implementation.written_files = ["app/main.py", "app/models.py"]
    prior.documentation.written_files = ["docs/README.md"]
    prior.documentation.generated_docs = [
        DocumentationFile(title="README", path="docs/README.md", content="# Expense Tracker")
    ]
    prior.knowledge.entries = [
        KnowledgeEntry(
            id="AD1",
            category=KnowledgeCategory.ARCHITECTURE_DECISION,
            title="Use FastAPI",
            content="Chosen for async support.",
            created_by="architect",
            status=KnowledgeStatus.ACTIVE,
        )
    ]
    prior.testing.passed = True
    prior.testing.status = TestStatus.PASSED
    prior.review.passed = True
    prior.review.score = 9.0
    prior.debug.failure_summary = "Some prior failure analysis"
    prior.execution.workflow_status = WorkflowStatus.COMPLETED
    prior.execution.current_agent = AgentType.DOCUMENTATION
    prior.execution.current_step = "Completed documentation agent"
    prior.execution.test_retry_count = 2
    prior.execution.review_retry_count = 1
    prior.execution.last_repair_trigger = RepairTrigger.TEST_FAILURE
    prior.execution.error_message = "some transient error"
    prior.execution.completed_at = datetime(2026, 1, 1, tzinfo=UTC)

    return prior


def test_seed_continuation_state_appends_the_new_message_not_replaces(run_service: RunService) -> None:
    prior = _prior_state_with_full_history()

    seeded = run_service.seed_continuation_state(prior, "Add authentication")

    assert [message.content for message in seeded.conversation.messages] == [
        "Build a fastapi expense tracker",
        "Add authentication",
    ]
    assert seeded.conversation.summary == "Initial expense tracker build."
    assert len(prior.conversation.messages) == 1


def test_seed_continuation_state_carries_forward_durable_context(run_service: RunService) -> None:
    prior = _prior_state_with_full_history()

    seeded = run_service.seed_continuation_state(prior, "Add authentication")

    assert seeded.project.project_name == "Expense Tracker"
    assert seeded.implementation.written_files == ["app/main.py", "app/models.py"]
    assert seeded.knowledge.entries[0].title == "Use FastAPI"


def test_seed_continuation_state_resets_documentation_but_keeps_written_files(
    run_service: RunService,
) -> None:
    prior = _prior_state_with_full_history()

    seeded = run_service.seed_continuation_state(prior, "Add authentication")

    assert seeded.documentation.generated_docs == []
    assert seeded.documentation.written_files == ["docs/README.md"]


def test_seed_continuation_state_resets_testing_debug_and_review(run_service: RunService) -> None:
    prior = _prior_state_with_full_history()

    seeded = run_service.seed_continuation_state(prior, "Add authentication")

    assert seeded.testing.passed is False
    assert seeded.testing.status == TestStatus.NOT_RUN
    assert seeded.review.passed is False
    assert seeded.review.score == 0.0
    assert seeded.debug.failure_summary is None


def test_seed_continuation_state_resets_execution_for_a_fresh_pass(run_service: RunService) -> None:
    prior = _prior_state_with_full_history()

    seeded = run_service.seed_continuation_state(prior, "Add authentication")

    assert seeded.execution.workflow_status == WorkflowStatus.RUNNING
    assert seeded.execution.current_agent is None
    assert seeded.execution.current_step is None
    assert seeded.execution.error_message is None
    assert seeded.execution.test_retry_count == 0
    assert seeded.execution.review_retry_count == 0
    assert seeded.execution.last_repair_trigger == RepairTrigger.NONE
    assert seeded.execution.completed_at is None
    assert seeded.execution.started_at > prior.execution.completed_at
