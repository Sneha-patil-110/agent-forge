from __future__ import annotations

import logging
from typing import Callable

from backend.events.event_types import WorkflowEvent

logger = logging.getLogger(__name__)

EventHandler = Callable[[WorkflowEvent], None]


class EventDispatcher:
    def __init__(self) -> None:
        self._subscribers: list[EventHandler] = []

    def subscribe(self, handler: EventHandler) -> None:
        self._subscribers.append(handler)

    def unsubscribe(self, handler: EventHandler) -> None:
        if handler in self._subscribers:
            self._subscribers.remove(handler)

    def emit(self, event: WorkflowEvent) -> None:
        for handler in list(self._subscribers):
            try:
                handler(event)
            except Exception:
                logger.exception(
                    "Event subscriber %r raised while handling %s; continuing.",
                    handler,
                    event.event_type.value,
                )
