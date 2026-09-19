
from __future__ import annotations

from pathlib import Path

import pytest

from backend.agents.debugger_agent import DebuggerAgent
from backend.agents.developer_agent import DeveloperAgent
from backend.agents.reviewer_agent import ReviewerAgent
from backend.core.constants import MAX_REVIEW_ATTEMPTS, MAX_REVIEW_RETRIES
from backend.core.exceptions import AgentExecutionError, AgentValidationError
from backend.events.dispatcher import EventDispatcher
from backend.events.event_types import EventType, WorkflowEvent
from backend.graph.builder import WorkflowBuilder
from backend.graph.nodes import WorkflowNodes
from backend.graph.router import WorkflowRouter
from backend.graph.workflow import WorkflowNode
from backend.services.materialization_service import MaterializationService
from backend.services.testing_service import TestingService
from backend.state.execution_state import WorkflowStatus
from backend.state.repository_snapshot import RepositorySnapshot
from backend.state.review_state import ReviewIssue, ReviewState, Severity
from backend.state.workflow_state import WorkflowState
from backend.tools.filesystem_tool import FilesystemTool
from backend.tools.terminal_tool import TerminalTool
from backend.tools.tool_registry import ToolRegistry
from backend.utils.run_id import generate_run_id

from tests.test_review_retry_integration import (
    DEBUG_ANALYSIS,
    REVIEW_PASSED,
    TESTER_ANALYSIS,
    VALID_ARCHITECTURE_STATE,
    VALID_DOCUMENTATION_STATE,
    VALID_PLANNING_STATE,
    VALID_PROJECT_STATE,
    WORKING_CALC_CONTENT,
    ScriptedLLMService,
    StubPromptService,
    _as_workflow_state,
    _calc_file,
    _implementation_payload,
    _initial_state,
    _test_file,
)


def _review_issue(*, title: str, severity: str, file_path: str = "calc.py") -> dict:
    return {
        "title": title,
        "description": f"{title} needs attention.",
        "severity": severity,
        "file_path": file_path,
        "suggestion": "Address the issue.",
    }


REVIEW_FAILED_STYLE_1 = {
    "passed": False,
    "score": 5.5,
    "issues": [_review_issue(title="Inconsistent naming", severity="medium")],
    "strengths": ["Correct arithmetic."],
    "recommendations": ["Adopt consistent naming."],
    "review_summary": "Functionally correct but has style issues.",
}

REVIEW_FAILED_STYLE_2 = {
    "passed": False,
    "score": 6.0,
    "issues": [_review_issue(title="Missing docstrings", severity="low")],
    "strengths": ["Correct arithmetic.", "Clear structure."],
    "recommendations": ["Add docstrings."],
    "review_summary": "Still missing documentation, otherwise solid.",
}

REVIEW_FAILED_CRITICAL = {
    "passed": False,
    "score": 2.0,
    "issues": [_review_issue(title="Hardcoded API credentials", severity="critical")],
    "strengths": [],
    "recommendations": [],
    "review_summary": "Exposed credentials found in source.",
}


def _build_workflow(
    *,
    reviewer_script: list[dict],
    output_directory: Path,
    event_dispatcher: EventDispatcher | None = None,
    run_id: str | None = None,
):

    llm_service = ScriptedLLMService(
        {
            "analysis": [VALID_PROJECT_STATE],
            "planner": [VALID_PLANNING_STATE],
            "architect": [VALID_ARCHITECTURE_STATE],
            "developer": [
                _implementation_payload(
                    _calc_file(WORKING_CALC_CONTENT, "Calculator module."),
                    _test_file(),
                )
            ],
            "tester": [TESTER_ANALYSIS],
            "debugger": [DEBUG_ANALYSIS],
            "reviewer": reviewer_script,
            "documentation": [VALID_DOCUMENTATION_STATE],
        }
    )
    prompt_service = StubPromptService()

    from backend.agents.analysis_agent import AnalysisAgent
    from backend.agents.architect_agent import ArchitectAgent
    from backend.agents.documenter_agent import DocumentationAgent
    from backend.agents.planner_agent import PlannerAgent
    from backend.agents.tester_agent import TesterAgent

    tool_registry = ToolRegistry()
    tool_registry.register(FilesystemTool(workspace=output_directory))
    tool_registry.register(TerminalTool(workspace=output_directory))

    nodes = WorkflowNodes(
        analysis_agent=AnalysisAgent(prompt_service, llm_service),
        planner_agent=PlannerAgent(prompt_service, llm_service),
        architect_agent=ArchitectAgent(prompt_service, llm_service),
        developer_agent=DeveloperAgent(prompt_service, llm_service),
        tester_agent=TesterAgent(prompt_service, llm_service),
        debugger_agent=DebuggerAgent(prompt_service, llm_service),
        reviewer_agent=ReviewerAgent(prompt_service, llm_service),
        documentation_agent=DocumentationAgent(prompt_service, llm_service),
        materialization_service=MaterializationService(tool_registry),
        testing_service=TestingService(tool_registry),
        event_dispatcher=event_dispatcher,
    )

    graph = WorkflowBuilder(nodes).build(event_dispatcher=event_dispatcher, run_id=run_id)

    return graph, llm_service


def _run(
    reviewer_script: list[dict], tmp_path: Path
) -> tuple[WorkflowState, ScriptedLLMService, list[WorkflowEvent]]:
    output_directory = tmp_path / "project"
    output_directory.mkdir()

    dispatcher = EventDispatcher()
    events: list[WorkflowEvent] = []
    dispatcher.subscribe(events.append)

    graph, llm_service = _build_workflow(
        reviewer_script=reviewer_script,
        output_directory=output_directory,
        event_dispatcher=dispatcher,
        run_id=generate_run_id(),
    )

    result = _as_workflow_state(
        graph.invoke(_initial_state(output_directory), config={"recursion_limit": 100})
    )

    return result, llm_service, events




def test_reviewer_passes_on_first_attempt(tmp_path: Path) -> None:
    result, llm_service, events = _run([REVIEW_PASSED], tmp_path)

    assert result.review.passed is True
    assert result.review.auto_passed is False
    assert result.review.attempt_number == 1
    assert result.execution.review_retry_count == 0
    assert llm_service.call_count("reviewer") == 1
    assert llm_service.call_count("developer") == 1
    assert llm_service.call_count("documentation") == 1
    assert result.execution.workflow_status == WorkflowStatus.COMPLETED

    assert any(e.event_type == EventType.REVIEWER_ATTEMPT_STARTED for e in events)
    assert any(e.event_type == EventType.REVIEWER_ATTEMPT_COMPLETED for e in events)
    assert not any(e.event_type == EventType.REVIEWER_AUTO_PASSED for e in events)
    assert not any(e.event_type == EventType.REVIEWER_REPAIR_REQUESTED for e in events)




def test_reviewer_fails_once_then_passes(tmp_path: Path) -> None:
    result, llm_service, events = _run([REVIEW_FAILED_STYLE_1, REVIEW_PASSED], tmp_path)

    assert result.review.passed is True
    assert result.review.auto_passed is False
    assert result.review.attempt_number == 2
    assert result.execution.review_retry_count == 1
    assert llm_service.call_count("reviewer") == 2
    assert llm_service.call_count("debugger") == 1
    assert llm_service.call_count("documentation") == 1
    assert result.execution.workflow_status == WorkflowStatus.COMPLETED

    repair_requested = [e for e in events if e.event_type == EventType.REVIEWER_REPAIR_REQUESTED]
    assert len(repair_requested) == 1
    auto_passed = [e for e in events if e.event_type == EventType.REVIEWER_AUTO_PASSED]
    assert auto_passed == []




def test_reviewer_fails_twice_then_auto_passes(tmp_path: Path) -> None:
    result, llm_service, events = _run(
        [REVIEW_FAILED_STYLE_1, REVIEW_FAILED_STYLE_2], tmp_path
    )

    assert result.review.passed is False, "the real verdict must never be rewritten to True"
    assert result.review.auto_passed is True
    assert result.review.auto_pass_reason == "review_attempt_limit_reached"
    assert result.review.attempt_number == MAX_REVIEW_ATTEMPTS
    assert result.execution.review_retry_count == MAX_REVIEW_ATTEMPTS

    assert llm_service.call_count("reviewer") == MAX_REVIEW_ATTEMPTS
    assert llm_service.call_count("debugger") == 1
    assert llm_service.call_count("developer") == 2
    assert llm_service.call_count("documentation") == 1

    assert result.execution.workflow_status == WorkflowStatus.COMPLETED
    assert result.documentation.generated_docs

    auto_passed_events = [e for e in events if e.event_type == EventType.REVIEWER_AUTO_PASSED]
    assert len(auto_passed_events) == 1
    meta = auto_passed_events[0].metadata
    assert meta["attempts"] == MAX_REVIEW_ATTEMPTS
    assert meta["original_verdict"] == "failed"
    assert meta["issue_count"] == 1
    assert meta["highest_severity"] == "low"
    assert meta["reason"] == "review_attempt_limit_reached"




def test_auto_pass_preserves_second_review_findings(tmp_path: Path) -> None:
    result, _, _ = _run([REVIEW_FAILED_STYLE_1, REVIEW_FAILED_STYLE_2], tmp_path)

    assert result.review.score == REVIEW_FAILED_STYLE_2["score"]
    assert result.review.review_summary == REVIEW_FAILED_STYLE_2["review_summary"]
    assert len(result.review.issues) == 1
    assert result.review.issues[0].title == "Missing docstrings"
    assert result.review.issues[0].severity == Severity.LOW
    assert result.review.issues[0].file_path == "calc.py"
    assert result.review.strengths == REVIEW_FAILED_STYLE_2["strengths"]




def test_auto_pass_does_not_touch_testing_result() -> None:
    class _StubReviewerAgent:
        def run(self, state: WorkflowState) -> WorkflowState:
            state.review = ReviewState(
                passed=False,
                score=4.0,
                issues=[ReviewIssue(title="t", description="d", severity=Severity.LOW)],
                attempt_number=state.execution.review_retry_count + 1,
            )
            return state

    nodes = WorkflowNodes(
        analysis_agent=None,
        planner_agent=None,
        architect_agent=None,
        developer_agent=None,
        tester_agent=None,
        debugger_agent=None,
        reviewer_agent=_StubReviewerAgent(),
        documentation_agent=None,
        materialization_service=None,
        testing_service=None,
    )

    state = WorkflowState()
    state.execution.review_retry_count = 1
    state.testing.passed = False
    state.testing.exit_code = 1

    result = nodes.reviewer(state)

    assert result.review.auto_passed is True
    assert result.testing.passed is False
    assert result.testing.exit_code == 1




def test_auto_pass_does_not_touch_repository_snapshot() -> None:
    class _StubReviewerAgent:
        def run(self, state: WorkflowState) -> WorkflowState:
            state.review = ReviewState(
                passed=False,
                score=4.0,
                issues=[ReviewIssue(title="t", description="d", severity=Severity.LOW)],
                attempt_number=state.execution.review_retry_count + 1,
            )
            return state

    nodes = WorkflowNodes(
        analysis_agent=None,
        planner_agent=None,
        architect_agent=None,
        developer_agent=None,
        tester_agent=None,
        debugger_agent=None,
        reviewer_agent=_StubReviewerAgent(),
        documentation_agent=None,
        materialization_service=None,
        testing_service=None,
    )

    state = WorkflowState()
    state.execution.review_retry_count = 1
    sentinel_snapshot = RepositorySnapshot(
        project_root="/fake/project",
        file_tree=["calc.py"],
    )
    state.repository_snapshot = sentinel_snapshot

    result = nodes.reviewer(state)

    assert result.review.auto_passed is True
    assert result.repository_snapshot is sentinel_snapshot




def test_critical_finding_never_auto_passes(tmp_path: Path) -> None:
    reviewer_script = [REVIEW_FAILED_CRITICAL] * (MAX_REVIEW_RETRIES + 1)

    result, llm_service, events = _run(reviewer_script, tmp_path)

    assert result.review.auto_passed is False
    assert result.review.auto_pass_reason is None
    assert result.review.passed is False
    assert result.execution.review_retry_count == MAX_REVIEW_RETRIES + 1
    assert result.execution.workflow_status == WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES

    assert llm_service.call_count("reviewer") == MAX_REVIEW_RETRIES + 1
    assert llm_service.call_count("documentation") == 0

    assert not any(e.event_type == EventType.REVIEWER_AUTO_PASSED for e in events)




def test_provider_failure_does_not_consume_review_attempt() -> None:
    class _ExplodingReviewerAgent:
        def run(self, state: WorkflowState) -> WorkflowState:
            raise AgentExecutionError("reviewer agent execution failed: provider outage")

    nodes = WorkflowNodes(
        analysis_agent=None,
        planner_agent=None,
        architect_agent=None,
        developer_agent=None,
        tester_agent=None,
        debugger_agent=None,
        reviewer_agent=_ExplodingReviewerAgent(),
        documentation_agent=None,
        materialization_service=None,
        testing_service=None,
    )

    state = WorkflowState()
    state.execution.review_retry_count = 0

    with pytest.raises(AgentExecutionError):
        nodes.reviewer(state)

    assert state.execution.review_retry_count == 0




def test_malformed_output_does_not_consume_review_attempt() -> None:
    class _MalformedReviewerAgent:
        def run(self, state: WorkflowState) -> WorkflowState:
            raise AgentValidationError(
                "Reviewer Agent output does not match ReviewState.",
                details={"validation_errors": []},
            )

    nodes = WorkflowNodes(
        analysis_agent=None,
        planner_agent=None,
        architect_agent=None,
        developer_agent=None,
        tester_agent=None,
        debugger_agent=None,
        reviewer_agent=_MalformedReviewerAgent(),
        documentation_agent=None,
        materialization_service=None,
        testing_service=None,
    )

    state = WorkflowState()
    state.execution.review_retry_count = 1

    with pytest.raises(AgentValidationError):
        nodes.reviewer(state)

    assert state.execution.review_retry_count == 1




def test_review_attempt_counter_survives_resume(tmp_path: Path) -> None:

    from backend.services.checkpoint_service import CheckpointService

    run_id = generate_run_id()
    output_directory = tmp_path / "project"
    output_directory.mkdir()

    checkpoint_service = CheckpointService(runs_root=tmp_path / "runs")
    config = {"configurable": {"thread_id": run_id}}

    dispatcher_a = EventDispatcher()
    checkpointer_a = checkpoint_service.checkpointer_for_run(run_id)
    graph_a = WorkflowBuilder(
        WorkflowNodes(
            **_nodes_kwargs_for_resume(
                output_directory, dispatcher_a, reviewer_script=[REVIEW_FAILED_STYLE_1]
            ),
        )
    ).build(
        checkpointer=checkpointer_a,
        event_dispatcher=dispatcher_a,
        run_id=run_id,
        interrupt_after=[WorkflowNode.DEBUGGER.value],
    )

    interrupted = _as_workflow_state(
        graph_a.invoke(
            _initial_state(output_directory),
            config={**config, "recursion_limit": 100},
        )
    )

    assert interrupted.review.attempt_number == 1
    assert interrupted.execution.review_retry_count == 1
    assert interrupted.review.auto_passed is False

    dispatcher_b = EventDispatcher()
    events_b: list[WorkflowEvent] = []
    dispatcher_b.subscribe(events_b.append)

    checkpointer_b = checkpoint_service.checkpointer_for_run(run_id)
    graph_b = WorkflowBuilder(
        WorkflowNodes(
            **_nodes_kwargs_for_resume(
                output_directory, dispatcher_b, reviewer_script=[REVIEW_FAILED_STYLE_2]
            )
        )
    ).build(
        checkpointer=checkpointer_b,
        event_dispatcher=dispatcher_b,
        run_id=run_id,
    )

    result = _as_workflow_state(
        graph_b.invoke(None, config={**config, "recursion_limit": 100})
    )

    reviewer_attempt_started_in_b = [
        e for e in events_b if e.event_type == EventType.REVIEWER_ATTEMPT_STARTED
    ]

    assert result.review.attempt_number == 2
    assert result.execution.review_retry_count == 2
    assert result.review.auto_passed is True
    assert result.review.auto_pass_reason == "review_attempt_limit_reached"
    assert result.execution.workflow_status == WorkflowStatus.COMPLETED
    assert len(reviewer_attempt_started_in_b) == 1
    assert reviewer_attempt_started_in_b[0].metadata["attempt"] == 2


def _nodes_kwargs_for_resume(
    output_directory: Path, dispatcher: EventDispatcher, *, reviewer_script: list[dict]
) -> dict:
    from backend.agents.analysis_agent import AnalysisAgent
    from backend.agents.architect_agent import ArchitectAgent
    from backend.agents.documenter_agent import DocumentationAgent
    from backend.agents.planner_agent import PlannerAgent
    from backend.agents.tester_agent import TesterAgent

    llm_service = ScriptedLLMService(
        {
            "analysis": [VALID_PROJECT_STATE],
            "planner": [VALID_PLANNING_STATE],
            "architect": [VALID_ARCHITECTURE_STATE],
            "developer": [
                _implementation_payload(
                    _calc_file(WORKING_CALC_CONTENT, "Calculator module."),
                    _test_file(),
                )
            ],
            "tester": [TESTER_ANALYSIS],
            "debugger": [DEBUG_ANALYSIS],
            "reviewer": reviewer_script,
            "documentation": [VALID_DOCUMENTATION_STATE],
        }
    )
    prompt_service = StubPromptService()

    tool_registry = ToolRegistry()
    tool_registry.register(FilesystemTool(workspace=output_directory))
    tool_registry.register(TerminalTool(workspace=output_directory))

    return dict(
        analysis_agent=AnalysisAgent(prompt_service, llm_service),
        planner_agent=PlannerAgent(prompt_service, llm_service),
        architect_agent=ArchitectAgent(prompt_service, llm_service),
        developer_agent=DeveloperAgent(prompt_service, llm_service),
        tester_agent=TesterAgent(prompt_service, llm_service),
        debugger_agent=DebuggerAgent(prompt_service, llm_service),
        reviewer_agent=ReviewerAgent(prompt_service, llm_service),
        documentation_agent=DocumentationAgent(prompt_service, llm_service),
        materialization_service=MaterializationService(tool_registry),
        testing_service=TestingService(tool_registry),
        event_dispatcher=dispatcher,
    )




def test_review_router_routes_auto_passed_to_documentation() -> None:
    state = WorkflowState()
    state.review = ReviewState(passed=False, auto_passed=True, attempt_number=2)

    assert WorkflowRouter.review_router(state) == WorkflowNode.DOCUMENTATION.value


def test_review_router_still_routes_plain_pass_to_documentation() -> None:
    state = WorkflowState()
    state.review = ReviewState(passed=True, attempt_number=1)

    assert WorkflowRouter.review_router(state) == WorkflowNode.DOCUMENTATION.value


def test_review_router_routes_genuine_failure_to_debugger() -> None:
    state = WorkflowState()
    state.review = ReviewState(passed=False, auto_passed=False, attempt_number=1)

    assert WorkflowRouter.review_router(state) == WorkflowNode.DEBUGGER.value
