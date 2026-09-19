
from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

from backend.services.repository_integrity_validator import RepositoryIntegrityValidator
from backend.services.run_service import RunService
from backend.state.execution_state import WorkflowStatus
from backend.state.workflow_state import WorkflowState


class ReplayResult(NamedTuple):
    original_run_id: str
    replay_run_id: str
    state: WorkflowState
    hash_mismatch_warning: str | None


class RepositoryNoLongerOnDiskError(Exception):
    pass


class ReplayService:
    def __init__(
        self,
        *,
        run_service: RunService,
        repository_integrity_validator: RepositoryIntegrityValidator,
        tester_node,
    ) -> None:
        self.run_service = run_service
        self.repository_integrity_validator = repository_integrity_validator
        self.tester_node = tester_node

    def replay_from_testing(self, run_id: str) -> ReplayResult:
        original_state = self.run_service.load_state(run_id)
        output_directory = original_state.project.output_directory

        if not output_directory or not Path(output_directory).is_dir():
            raise RepositoryNoLongerOnDiskError(
                f"Run {run_id}'s repository is no longer on disk "
                f"(output_directory={output_directory!r}); nothing to replay."
            )

        fresh_snapshot = self.repository_integrity_validator.create_snapshot(
            output_directory, state=original_state
        )
        saved_snapshot = original_state.repository_snapshot

        hash_mismatch_warning: str | None = None
        if (
            saved_snapshot
            and saved_snapshot.content_hash
            and fresh_snapshot.content_hash != saved_snapshot.content_hash
        ):
            hash_mismatch_warning = (
                "Repository content on disk no longer matches the snapshot "
                f"saved with run {run_id} "
                f"(saved={saved_snapshot.content_hash[:12]}, "
                f"current={fresh_snapshot.content_hash[:12]}). "
                "Replaying against the CURRENT on-disk content anyway -- "
                "results may not reproduce the original failure."
            )

        replay_state = original_state.model_copy(deep=True)
        replay_state.repository_snapshot = fresh_snapshot
        replay_state.execution.workflow_status = WorkflowStatus.RUNNING
        replay_state.execution.error_message = None
        replay_state.execution.test_retry_count = 0
        replay_state.execution.completed_at = None

        replay_state = self.tester_node(replay_state)

        replay_metadata = self.run_service.create_run()
        self.run_service.save_state(replay_metadata.run_id, replay_state)

        return ReplayResult(
            original_run_id=run_id,
            replay_run_id=replay_metadata.run_id,
            state=replay_state,
            hash_mismatch_warning=hash_mismatch_warning,
        )
