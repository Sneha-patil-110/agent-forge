
from __future__ import annotations

from backend.graph.workflow import WorkflowNode


WORKFLOW_EDGES = (
    (WorkflowNode.ANALYSIS, WorkflowNode.PLANNER),
    (WorkflowNode.PLANNER, WorkflowNode.ARCHITECT),
    (WorkflowNode.ARCHITECT, WorkflowNode.DEVELOPER),
    (WorkflowNode.DEVELOPER, WorkflowNode.STATIC_VALIDATION),
    (WorkflowNode.DEBUGGER, WorkflowNode.DEVELOPER),
)
