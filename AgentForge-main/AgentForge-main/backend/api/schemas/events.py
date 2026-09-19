from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class EventOut(BaseModel):
    id: int
    run_id: str
    event_type: str
    agent: str | None
    message: str | None
    metadata: dict[str, Any]
    timestamp: datetime


class EventList(BaseModel):
    events: list[EventOut]