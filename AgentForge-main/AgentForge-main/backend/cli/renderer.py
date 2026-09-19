from __future__ import annotations

import sys
from typing import TextIO

from backend.events.event_types import EventType, WorkflowEvent

_MESSAGE_TEMPLATES: dict[EventType, str] = {
    EventType.WORKFLOW_STARTED: "Workflow started",
    EventType.WORKFLOW_RESUMED: "Workflow resumed",
    EventType.AGENT_STARTED: "{agent} started",
    EventType.AGENT_COMPLETED: "{agent} completed",
    EventType.TESTING_PASSED: "Testing passed",
    EventType.TESTING_FAILED: "Testing failed",
    EventType.REVIEW_PASSED: "Review passed",
    EventType.REVIEW_FAILED: "Review failed",
    EventType.WORKFLOW_COMPLETED: "Workflow completed",
    EventType.WORKFLOW_INTERRUPTED: "Workflow interrupted",
    EventType.WORKFLOW_FAILED: "Workflow failed",
    EventType.MCP_TOOL_CALL_STARTED: "{agent} calling tool {tool}",
    EventType.MCP_TOOL_CALL_COMPLETED: "{agent} finished tool {tool}",
    EventType.MCP_TOOL_CALL_FAILED: "{agent} tool {tool} failed",
}


class CLIEventRenderer:
    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream or sys.stdout

    def __call__(self, event: WorkflowEvent) -> None:
        template = _MESSAGE_TEMPLATES.get(event.event_type, event.event_type.value)
        agent_name = event.agent.value.capitalize() if event.agent else ""
        tool_name = event.metadata.get("tool", "")
        text = template.format(agent=agent_name, tool=tool_name)

        if event.event_type in (EventType.WORKFLOW_FAILED, EventType.MCP_TOOL_CALL_FAILED) and event.message:
            text = f"{text}: {event.message}"

        print(text, file=self._stream)
