from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage
from sqlalchemy.orm import Session, sessionmaker

if TYPE_CHECKING:
    from backend.state.failure_bundle import FailureBundle

from backend.core.exceptions import (
    InvalidRunIdError,
    RunCorruptedError,
    RunError,
    RunNotFoundError,
)
from backend.core.workspace import RUNS_ROOT
from backend.repositories.run_repository import RunRepository
from backend.state.debug_state import DebugState
from backend.state.documentation_state import DocumentationState
from backend.state.execution_state import RepairTrigger, WorkflowStatus
from backend.state.review_state import ReviewState
from backend.state.run_metadata import RunMetadata
from backend.state.testing_state import TestingState
from backend.state.workflow_state import WorkflowState
from backend.utils.atomic_io import atomic_write_text
from backend.utils.run_id import generate_run_id, validate_run_id

logger = logging.getLogger(__name__)

METADATA_FILENAME = "metadata.json"
STATE_FILENAME = "state.json"
FAILURE_BUNDLE_FILENAME = "failure_bundle.json"

_MAX_RUN_ID_ATTEMPTS = 5
_READ_RETRY_ATTEMPTS = 5
_READ_RETRY_DELAY_SECONDS = 0.02


def _read_text_with_retry(path: Path, *, encoding: str = "utf-8") -> str:
    last_error: OSError | None = None

    for attempt in range(_READ_RETRY_ATTEMPTS):
        try:
            return path.read_text(encoding=encoding)
        except PermissionError as error:
            last_error = error
            if attempt < _READ_RETRY_ATTEMPTS - 1:
                time.sleep(_READ_RETRY_DELAY_SECONDS)

    raise last_error


class RunService:
    def __init__(
        self,
        runs_root: Path = RUNS_ROOT,
        *,
        db_session_factory: sessionmaker[Session] | None = None,
    ) -> None:
        self.runs_root = Path(runs_root).resolve()
        self.runs_root.mkdir(parents=True, exist_ok=True)
        self.db_session_factory = db_session_factory

    def run_dir(self, run_id: str) -> Path:
        validate_run_id(run_id)
        run_dir = (self.runs_root / run_id).resolve()

        try:
            run_dir.relative_to(self.runs_root)
        except ValueError as error:
            raise InvalidRunIdError(
                f"Resolved run directory for {run_id!r} escapes the runs root.",
                details={"run_id": run_id},
            ) from error

        return run_dir

    def create_run(
        self, *, owner_id: str | None = None, project_id: str | None = None
    ) -> RunMetadata:
        last_error: OSError | None = None

        for _ in range(_MAX_RUN_ID_ATTEMPTS):
            run_id = generate_run_id()
            run_dir = self.run_dir(run_id)

            try:
                run_dir.mkdir(parents=True, exist_ok=False)
            except FileExistsError as error:
                last_error = error
                continue

            metadata = RunMetadata(run_id=run_id, owner_id=owner_id, project_id=project_id)
            state = WorkflowState()
            self._write_metadata(run_dir, metadata)
            self._write_state(run_dir, state)
            self._persist_blob(run_id, metadata=metadata, state=state)

            logger.info("Run created: %s", run_id)
            return metadata

        raise RunError(
            "Failed to allocate a unique run ID.",
            details={"attempts": _MAX_RUN_ID_ATTEMPTS},
        ) from last_error

    def seed_continuation_state(self, prior: WorkflowState, new_message: str) -> WorkflowState:

        state = prior.model_copy(deep=True)

        state.conversation.messages = [
            *state.conversation.messages,
            HumanMessage(content=new_message),
        ]

        state.testing = TestingState()
        state.debug = DebugState()
        state.review = ReviewState()

        state.documentation = DocumentationState(
            written_files=state.documentation.written_files,
        )

        state.execution.workflow_status = WorkflowStatus.RUNNING
        state.execution.current_agent = None
        state.execution.current_step = None
        state.execution.error_message = None
        state.execution.test_retry_count = 0
        state.execution.review_retry_count = 0
        state.execution.last_repair_trigger = RepairTrigger.NONE
        state.execution.started_at = datetime.now(UTC)
        state.execution.completed_at = None

        return state

    def validate_resume_state(self, state: WorkflowState) -> WorkflowState:
        if state.project.output_directory:
            out_path = Path(state.project.output_directory).resolve()
            out_path.mkdir(parents=True, exist_ok=True)
            state.project.output_directory = str(out_path)
        return state


    def seed_restart_state(self, prior: WorkflowState) -> WorkflowState:

        original_message = prior.conversation.messages[0] if prior.conversation.messages else None

        state = WorkflowState()

        if original_message is not None:
            state.conversation.messages = [original_message]

        state.project.output_directory = prior.project.output_directory

        return state

    def run_exists(self, run_id: str) -> bool:
        return self.run_dir(run_id).exists()

    def list_run_ids(self) -> list[str]:

        if not self.runs_root.exists():
            return []

        run_ids = []

        for entry in self.runs_root.iterdir():
            if not entry.is_dir():
                continue

            try:
                validate_run_id(entry.name)
            except InvalidRunIdError:
                continue

            run_ids.append(entry.name)

        return run_ids

    def save_state(self, run_id: str, state: WorkflowState) -> None:

        run_dir = self.run_dir(run_id)

        if not run_dir.exists() and not self._rehydrate_from_db(run_id):
            raise RunNotFoundError(
                f"Run not found: {run_id}", details={"run_id": run_id}
            )

        self._write_state(run_dir, state)

        metadata = self.load_metadata(run_id)
        metadata.updated_at = datetime.now(UTC)
        self._write_metadata(run_dir, metadata)
        self._persist_blob(run_id, metadata=metadata, state=state)

    def load_state(self, run_id: str) -> WorkflowState:
        run_dir = self.run_dir(run_id)
        state_path = run_dir / STATE_FILENAME

        if not state_path.exists():
            self._rehydrate_from_db(run_id)

        if not state_path.exists():
            raise RunNotFoundError(
                f"Run not found: {run_id}", details={"run_id": run_id}
            )

        try:
            text = _read_text_with_retry(state_path)
            return WorkflowState.model_validate_json(text)
        except (OSError, ValueError) as error:
            raise RunCorruptedError(
                f"Run state for '{run_id}' could not be read: {error}",
                details={"run_id": run_id},
            ) from error

    def save_failure_bundle(self, run_id: str, bundle: "FailureBundle") -> None:

        run_dir = self.run_dir(run_id)

        if not run_dir.exists():
            raise RunNotFoundError(
                f"Run not found: {run_id}", details={"run_id": run_id}
            )

        atomic_write_text(
            run_dir / FAILURE_BUNDLE_FILENAME,
            bundle.model_dump_json(indent=2),
        )

    def load_failure_bundle(self, run_id: str) -> "FailureBundle | None":

        from backend.state.failure_bundle import FailureBundle

        run_dir = self.run_dir(run_id)
        bundle_path = run_dir / FAILURE_BUNDLE_FILENAME

        if not bundle_path.exists():
            return None

        try:
            text = _read_text_with_retry(bundle_path)
            return FailureBundle.model_validate_json(text)
        except (OSError, ValueError) as error:
            raise RunCorruptedError(
                f"Failure bundle for '{run_id}' could not be read: {error}",
                details={"run_id": run_id},
            ) from error

    def load_metadata(self, run_id: str) -> RunMetadata:
        run_dir = self.run_dir(run_id)
        metadata_path = run_dir / METADATA_FILENAME

        if not metadata_path.exists():
            self._rehydrate_from_db(run_id)

        if not metadata_path.exists():
            raise RunNotFoundError(
                f"Run not found: {run_id}", details={"run_id": run_id}
            )

        try:
            text = _read_text_with_retry(metadata_path)
            return RunMetadata.model_validate_json(text)
        except (OSError, ValueError) as error:
            raise RunCorruptedError(
                f"Run metadata for '{run_id}' could not be read: {error}",
                details={"run_id": run_id},
            ) from error

    @staticmethod
    def _write_metadata(run_dir: Path, metadata: RunMetadata) -> None:
        atomic_write_text(
            run_dir / METADATA_FILENAME,
            metadata.model_dump_json(indent=2),
        )

    @staticmethod
    def _write_state(run_dir: Path, state: WorkflowState) -> None:
        atomic_write_text(
            run_dir / STATE_FILENAME,
            state.model_dump_json(indent=2),
        )

    def _persist_blob(self, run_id: str, *, metadata: RunMetadata, state: WorkflowState) -> None:
        if self.db_session_factory is None:
            return

        try:
            with self.db_session_factory() as session:
                RunRepository(session).upsert_blob(
                    run_id=run_id,
                    state_json=state.model_dump_json(),
                    metadata_json=metadata.model_dump_json(),
                    created_at=metadata.created_at,
                    updated_at=datetime.now(UTC),
                )
                session.commit()
        except Exception:
            logger.warning(
                "Failed to persist durable state/metadata for run %s; continuing without it.",
                run_id,
                exc_info=True,
            )

    def _rehydrate_from_db(self, run_id: str) -> bool:
        """Restore state.json/metadata.json from Postgres when local disk lost them.

        The app container's local disk is ephemeral (wiped on redeploy/restart),
        while the JSON blobs mirrored to Postgres by `_persist_blob` survive.
        Without this, any run created before the most recent restart 404s on
        every route even though its DB row (and mirrored content) still exists.
        """
        if self.db_session_factory is None:
            return False

        try:
            with self.db_session_factory() as session:
                record = RunRepository(session).get(run_id)

                if record is None or (record.state_json is None and record.run_metadata_json is None):
                    return False

                run_dir = self.run_dir(run_id)
                run_dir.mkdir(parents=True, exist_ok=True)
                restored = False

                if record.state_json is not None and not (run_dir / STATE_FILENAME).exists():
                    atomic_write_text(run_dir / STATE_FILENAME, record.state_json)
                    restored = True

                if record.run_metadata_json is not None and not (run_dir / METADATA_FILENAME).exists():
                    atomic_write_text(run_dir / METADATA_FILENAME, record.run_metadata_json)
                    restored = True

                if restored:
                    logger.warning(
                        "Rehydrated run %s from Postgres after local files were missing.", run_id
                    )

                return restored
        except Exception:
            logger.warning("Failed to rehydrate run %s from Postgres.", run_id, exc_info=True)
            return False
