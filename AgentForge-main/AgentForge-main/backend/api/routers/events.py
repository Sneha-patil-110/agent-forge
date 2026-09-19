
from __future__ import annotations

import json
import queue
import time
from typing import Iterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from backend.api.dependencies import get_application, get_current_user_for_sse
from backend.core.app import Application
from backend.db.models.user import User
from backend.events.event_types import EventType, WorkflowEvent
from backend.repositories.event_repository import EventRepository

router = APIRouter(prefix="/api/v1/runs", tags=["events"])

_HEARTBEAT_SECONDS = 15.0
_MAX_STREAM_SECONDS = 60 * 30

_TERMINAL_EVENT_VALUES = frozenset(
    {EventType.WORKFLOW_COMPLETED.value, EventType.WORKFLOW_FAILED.value, EventType.WORKFLOW_INTERRUPTED.value}
)


def _format_sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _load_history(application: Application, run_id: str) -> Iterator[tuple[str, str]]:
    if application.db_session_factory is None:
        return

    try:
        with application.db_session_factory() as session:
            records = EventRepository(session).list_for_run(run_id)
    except Exception:
        return

    for record in records:
        line = _format_sse(
            {
                "id": record.id,
                "run_id": record.run_id,
                "event_type": record.event_type,
                "agent": record.agent,
                "message": record.message,
                "metadata": record.event_metadata,
                "timestamp": record.timestamp.isoformat(),
            }
        )
        yield line, record.event_type


@router.get("/{run_id}/events")
def stream_run_events(
    run_id: str,
    application: Application = Depends(get_application),
    current_user: User = Depends(get_current_user_for_sse),
) -> StreamingResponse:
    metadata = application.run_service.load_metadata(run_id)

    if metadata.owner_id is None or metadata.owner_id != str(current_user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run not found: {run_id}")

    event_queue: queue.Queue[WorkflowEvent] = queue.Queue()

    def _on_event(event: WorkflowEvent) -> None:
        if event.run_id == run_id:
            event_queue.put(event)

    def _generate() -> Iterator[str]:
        application.event_dispatcher.subscribe(_on_event)

        try:
            for line, event_type in _load_history(application, run_id):
                yield line

                if event_type in _TERMINAL_EVENT_VALUES:
                    return

            deadline = time.monotonic() + _MAX_STREAM_SECONDS

            while time.monotonic() < deadline:
                try:
                    event = event_queue.get(timeout=_HEARTBEAT_SECONDS)
                except queue.Empty:
                    yield ": heartbeat\n\n"
                    continue

                yield _format_sse(event.model_dump(mode="json"))

                if event.event_type.value in _TERMINAL_EVENT_VALUES:
                    return
        finally:
            application.event_dispatcher.unsubscribe(_on_event)

    return StreamingResponse(_generate(), media_type="text/event-stream")