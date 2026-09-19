from __future__ import annotations

from langgraph.graph import END, START

from backend.graph.builder import WorkflowBuilder
from backend.graph.nodes import WorkflowNodes
from backend.graph.workflow import WorkflowNode


class _NoopAgent:
    def run(self, state):
        return state


def _build_graph():
    nodes = WorkflowNodes(
        analysis_agent=_NoopAgent(),
        planner_agent=_NoopAgent(),
        architect_agent=_NoopAgent(),
        developer_agent=_NoopAgent(),
        tester_agent=_NoopAgent(),
        debugger_agent=_NoopAgent(),
        reviewer_agent=_NoopAgent(),
        documentation_agent=_NoopAgent(),
        materialization_service=None,
        testing_service=None,
    )

    return WorkflowBuilder(nodes).build()


def test_graph_compiles() -> None:
    graph = _build_graph()

    assert graph is not None


def test_every_expected_node_exists() -> None:
    graph = _build_graph()

    node_names = set(graph.get_graph().nodes.keys())

    expected = {
        "__start__",
        "__end__",
        WorkflowNode.ANALYSIS.value,
        WorkflowNode.PLANNER.value,
        WorkflowNode.ARCHITECT.value,
        WorkflowNode.DEVELOPER.value,
        WorkflowNode.STATIC_VALIDATION.value,
        WorkflowNode.TESTER.value,
        WorkflowNode.DEBUGGER.value,
        WorkflowNode.REVIEWER.value,
        WorkflowNode.DOCUMENTATION.value,
    }

    assert expected.issubset(node_names)
    assert node_names == expected, f"Unexpected extra nodes: {node_names - expected}"


def _edge_pairs(graph):
    return {
        (edge.source, edge.target)
        for edge in graph.get_graph().edges
    }


def test_start_routes_to_analysis() -> None:
    edges = _edge_pairs(_build_graph())

    assert (START, WorkflowNode.ANALYSIS.value) in edges


def test_analysis_routes_to_planner() -> None:
    edges = _edge_pairs(_build_graph())

    assert (
        WorkflowNode.ANALYSIS.value,
        WorkflowNode.PLANNER.value,
    ) in edges


def test_planner_routes_to_architect() -> None:
    edges = _edge_pairs(_build_graph())

    assert (
        WorkflowNode.PLANNER.value,
        WorkflowNode.ARCHITECT.value,
    ) in edges


def test_architect_routes_to_developer() -> None:
    edges = _edge_pairs(_build_graph())

    assert (
        WorkflowNode.ARCHITECT.value,
        WorkflowNode.DEVELOPER.value,
    ) in edges


def test_developer_routes_to_static_validation() -> None:
    edges = _edge_pairs(_build_graph())

    assert (
        WorkflowNode.DEVELOPER.value,
        WorkflowNode.STATIC_VALIDATION.value,
    ) in edges


def test_static_validation_has_conditional_edges_to_tester_debugger_and_end() -> None:
    graph = _build_graph()
    edges = _edge_pairs(graph)

    static_validation_targets = {
        target for source, target in edges if source == WorkflowNode.STATIC_VALIDATION.value
    }

    assert WorkflowNode.TESTER.value in static_validation_targets
    assert WorkflowNode.DEBUGGER.value in static_validation_targets
    assert END in static_validation_targets


def test_debugger_routes_to_developer() -> None:
    edges = _edge_pairs(_build_graph())

    assert (
        WorkflowNode.DEBUGGER.value,
        WorkflowNode.DEVELOPER.value,
    ) in edges


def test_tester_has_conditional_edges_to_reviewer_debugger_and_end() -> None:
    graph = _build_graph()
    edges = _edge_pairs(graph)

    tester_targets = {
        target for source, target in edges if source == WorkflowNode.TESTER.value
    }

    assert WorkflowNode.REVIEWER.value in tester_targets
    assert WorkflowNode.DEBUGGER.value in tester_targets
    assert END in tester_targets


def test_reviewer_has_conditional_edges_to_documentation_debugger_and_end() -> None:
    graph = _build_graph()
    edges = _edge_pairs(graph)

    reviewer_targets = {
        target for source, target in edges if source == WorkflowNode.REVIEWER.value
    }

    assert WorkflowNode.DOCUMENTATION.value in reviewer_targets
    assert WorkflowNode.DEBUGGER.value in reviewer_targets
    assert END in reviewer_targets


def test_tester_to_reviewer_edge_is_conditional_not_unconditional() -> None:
    graph = _build_graph()
    graph_edges = graph.get_graph().edges

    tester_to_reviewer = [
        edge
        for edge in graph_edges
        if edge.source == WorkflowNode.TESTER.value
        and edge.target == WorkflowNode.REVIEWER.value
    ]

    assert len(tester_to_reviewer) == 1
    assert tester_to_reviewer[0].conditional is True


def test_reviewer_to_documentation_edge_is_conditional_not_unconditional() -> None:

    graph = _build_graph()
    graph_edges = graph.get_graph().edges

    reviewer_to_documentation = [
        edge
        for edge in graph_edges
        if edge.source == WorkflowNode.REVIEWER.value
        and edge.target == WorkflowNode.DOCUMENTATION.value
    ]

    assert len(reviewer_to_documentation) == 1
    assert reviewer_to_documentation[0].conditional is True


def test_documentation_routes_to_end() -> None:
    edges = _edge_pairs(_build_graph())

    assert (WorkflowNode.DOCUMENTATION.value, END) in edges


def test_no_unreachable_nodes() -> None:
    graph = _build_graph()
    graph_repr = graph.get_graph()

    reachable = {START}
    frontier = [START]

    while frontier:
        current = frontier.pop()
        for edge in graph_repr.edges:
            if edge.source == current and edge.target not in reachable:
                reachable.add(edge.target)
                frontier.append(edge.target)

    all_nodes = set(graph_repr.nodes.keys())

    assert all_nodes.issubset(reachable), (
        f"Unreachable nodes: {all_nodes - reachable}"
    )


def test_no_edge_out_of_developer_directly_to_reviewer() -> None:

    edges = _edge_pairs(_build_graph())

    assert (
        WorkflowNode.DEVELOPER.value,
        WorkflowNode.REVIEWER.value,
    ) not in edges


def test_no_edge_out_of_developer_directly_to_documentation() -> None:
    edges = _edge_pairs(_build_graph())

    assert (
        WorkflowNode.DEVELOPER.value,
        WorkflowNode.DOCUMENTATION.value,
    ) not in edges


def test_no_edge_out_of_tester_directly_to_documentation() -> None:

    edges = _edge_pairs(_build_graph())

    assert (
        WorkflowNode.TESTER.value,
        WorkflowNode.DOCUMENTATION.value,
    ) not in edges


def test_no_edge_out_of_debugger_directly_to_reviewer() -> None:

    edges = _edge_pairs(_build_graph())

    assert (
        WorkflowNode.DEBUGGER.value,
        WorkflowNode.REVIEWER.value,
    ) not in edges


def test_debugger_only_routed_to_from_tester_static_validation_or_reviewer() -> None:
    edges = _edge_pairs(_build_graph())

    sources_into_debugger = {
        source for source, target in edges if target == WorkflowNode.DEBUGGER.value
    }

    assert sources_into_debugger == {
        WorkflowNode.TESTER.value,
        WorkflowNode.STATIC_VALIDATION.value,
        WorkflowNode.REVIEWER.value,
    }
