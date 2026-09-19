
from __future__ import annotations

import enum
import logging
import sqlite3
import tempfile
import typing
from datetime import UTC, datetime
from pathlib import Path

from langchain_core.messages import (
    AIMessage,
    ChatMessage,
    FunctionMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from backend.core.workspace import RUNS_ROOT
from backend.state.workflow_state import WorkflowState
from backend.utils.run_id import validate_run_id


class CheckpointInfo(BaseModel):
    checkpoint_id: str
    node_name: str | None = None
    timestamp: str | None = None

_CONCRETE_MESSAGE_CLASSES = (
    AIMessage,
    ChatMessage,
    FunctionMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

logger = logging.getLogger(__name__)

CHECKPOINT_FILENAME = "checkpoints.sqlite"


def _read_sqlite_bytes(db_path: Path) -> bytes:
    source = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir) / "backup.sqlite"
            dest = sqlite3.connect(str(tmp_path))

            try:
                source.backup(dest)
            finally:
                dest.close()

            return tmp_path.read_bytes()
    finally:
        source.close()


def _unwrap_annotation(annotation: typing.Any) -> list[typing.Any]:
    origin = typing.get_origin(annotation)

    if origin is None:
        return [annotation]

    unwrapped = []

    for arg in typing.get_args(annotation):
        if arg is type(None):
            continue
        unwrapped.extend(_unwrap_annotation(arg))

    return unwrapped


def _collect_state_classes(
    model_cls: type[BaseModel],
    seen: set[type] | None = None,
) -> set[type]:
    if seen is None:
        seen = set()

    if model_cls in seen:
        return seen

    seen.add(model_cls)

    for field in model_cls.model_fields.values():
        for candidate in _unwrap_annotation(field.annotation):
            if not isinstance(candidate, type) or candidate in seen:
                continue

            if issubclass(candidate, BaseModel):
                _collect_state_classes(candidate, seen)
            elif issubclass(candidate, enum.Enum):
                seen.add(candidate)

    return seen


class CheckpointService:
    def __init__(
        self,
        runs_root: Path = RUNS_ROOT,
        *,
        db_session_factory: sessionmaker[Session] | None = None,
    ) -> None:
        self.runs_root = Path(runs_root).resolve()
        self.db_session_factory = db_session_factory
        allowed_classes = _collect_state_classes(WorkflowState) | set(
            _CONCRETE_MESSAGE_CLASSES
        )
        self._serde = JsonPlusSerializer(
            allowed_msgpack_modules=list(allowed_classes),
        )

    def checkpointer_for_run(self, run_id: str) -> SqliteSaver:
        validate_run_id(run_id)

        run_dir = (self.runs_root / run_id).resolve()
        run_dir.relative_to(self.runs_root)
        run_dir.mkdir(parents=True, exist_ok=True)

        db_path = run_dir / CHECKPOINT_FILENAME

        if not db_path.exists():
            self._rehydrate_from_db(run_id, db_path)

        connection = sqlite3.connect(str(db_path), check_same_thread=False)
        saver = SqliteSaver(connection, serde=self._serde)
        saver.setup()

        logger.info("Checkpointer ready for run %s at %s", run_id, db_path)

        return saver

    def sync_to_db(self, run_id: str) -> None:
        if self.db_session_factory is None:
            return

        db_path = (self.runs_root / run_id).resolve() / CHECKPOINT_FILENAME

        if not db_path.exists():
            return

        try:
            blob = _read_sqlite_bytes(db_path)
        except Exception:
            logger.warning("Failed to read checkpoint file for run %s", run_id, exc_info=True)
            return

        try:
            from backend.repositories.run_repository import RunRepository

            with self.db_session_factory() as session:
                RunRepository(session).upsert_checkpoint_blob(
                    run_id=run_id,
                    checkpoint_blob=blob,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
                session.commit()
        except Exception:
            logger.warning(
                "Failed to persist checkpoint blob for run %s; continuing without it.",
                run_id,
                exc_info=True,
            )

    def _rehydrate_from_db(self, run_id: str, db_path: Path) -> None:
        if self.db_session_factory is None:
            return

        try:
            from backend.repositories.run_repository import RunRepository

            with self.db_session_factory() as session:
                record = RunRepository(session).get(run_id)

                if record is None or record.checkpoint_blob is None:
                    return

                db_path.parent.mkdir(parents=True, exist_ok=True)
                db_path.write_bytes(record.checkpoint_blob)

                logger.warning(
                    "Rehydrated checkpoint file for run %s from Postgres after local files were missing.",
                    run_id,
                )
        except Exception:
            logger.warning(
                "Failed to rehydrate checkpoint file for run %s from Postgres.", run_id, exc_info=True
            )

    def list_checkpoints(self, run_id: str) -> list[CheckpointInfo]:

        saver = self.checkpointer_for_run(run_id)
        config = {"configurable": {"thread_id": run_id}}
        infos: list[CheckpointInfo] = []

        for checkpoint_tuple in saver.list(config):
            checkpoint_id = checkpoint_tuple.config.get("configurable", {}).get("checkpoint_id")

            if checkpoint_id is None:
                continue

            node_name = self._node_name(checkpoint_tuple)

            infos.append(
                CheckpointInfo(
                    checkpoint_id=checkpoint_id,
                    node_name=node_name,
                    timestamp=checkpoint_tuple.checkpoint.get("ts"),
                )
            )

        return infos

    @staticmethod
    def _node_name(checkpoint_tuple) -> str | None:

        try:
            execution = checkpoint_tuple.checkpoint.get("channel_values", {}).get("execution")
            current_agent = getattr(execution, "current_agent", None)

            return current_agent.value if current_agent is not None else None
        except Exception:
            return None
