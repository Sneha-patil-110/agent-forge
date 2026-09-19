from __future__ import annotations

from pydantic import BaseModel


class WorkflowEdgeOut(BaseModel):
    source: str
    target: str
    conditional: bool


class WorkflowGraphOut(BaseModel):
    nodes: list[str]
    edges: list[WorkflowEdgeOut]
    repair_nodes: list[str]
