
from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.api.dependencies import get_application, get_current_user
from backend.api.schemas.workflow_graph import WorkflowEdgeOut, WorkflowGraphOut
from backend.core.app import Application
from backend.db.models.user import User
from backend.graph.workflow import WorkflowNode

router = APIRouter(prefix="/api/v1/workflow", tags=["workflow"])

_PSEUDO_NODES = frozenset({"__start__", "__end__"})


@router.get("/graph", response_model=WorkflowGraphOut)
def get_workflow_graph(
    application: Application = Depends(get_application),
    current_user: User = Depends(get_current_user),
) -> WorkflowGraphOut:
    compiled = application.workflow.build()
    graph_repr = compiled.get_graph()

    node_order = [node.value for node in WorkflowNode]
    order_index = {name: index for index, name in enumerate(node_order)}

    edges = [
        WorkflowEdgeOut(source=edge.source, target=edge.target, conditional=edge.conditional)
        for edge in graph_repr.edges
        if edge.source not in _PSEUDO_NODES and edge.target not in _PSEUDO_NODES
    ]

    repair_nodes = sorted(
        {
            edge.source
            for edge in edges
            if edge.source in order_index
            and edge.target in order_index
            and order_index[edge.target] <= order_index[edge.source]
        }
    )

    return WorkflowGraphOut(nodes=node_order, edges=edges, repair_nodes=repair_nodes)
