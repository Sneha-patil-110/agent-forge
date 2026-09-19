
from __future__ import annotations

from pathlib import Path

from backend.agents.analysis_agent import AnalysisAgent
from backend.agents.architect_agent import ArchitectAgent
from backend.agents.debugger_agent import DebuggerAgent
from backend.agents.developer_agent import DeveloperAgent
from backend.agents.documenter_agent import DocumentationAgent
from backend.agents.planner_agent import PlannerAgent
from backend.agents.reviewer_agent import ReviewerAgent
from backend.agents.tester_agent import TesterAgent
from backend.events.dispatcher import EventDispatcher
from backend.events.event_types import EventType, WorkflowEvent
from backend.graph.builder import WorkflowBuilder
from backend.graph.nodes import WorkflowNodes
from backend.services.materialization_service import MaterializationService
from backend.services.testing_service import TestingService
from backend.state.execution_state import AgentType, WorkflowStatus
from backend.state.workflow_state import WorkflowState
from backend.tools.filesystem_tool import FilesystemTool
from backend.tools.terminal_tool import TerminalTool
from backend.tools.tool_registry import ToolRegistry

from tests.test_review_retry_integration import (
    ALWAYS_FAILING_TEST_CONTENT,
    BROKEN_CALC_CONTENT,
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

RUN_ID = "af_20260714_deadbeef"


def _build_workflow_with_events(
    *,
    developer_script: list[dict],
    tester_script: list[dict],
    reviewer_script: list[dict],
    debugger_script: list[dict],
    output_directory: Path,
    review_failure_script: list[dict] | None = None,
):
    llm_service = ScriptedLLMService(
        {
            "analysis": [VALID_PROJECT_STATE],
            "planner": [VALID_PLANNING_STATE],
            "architect": [VALID_ARCHITECTURE_STATE],
            "developer": developer_script,
            "tester": tester_script,
            "debugger": debugger_script,
            "reviewer": reviewer_script if review_failure_script is None else review_failure_script,
            "documentation": [VALID_DOCUMENTATION_STATE],
        }
    )
    prompt_service = StubPromptService()

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
    )

    dispatcher = EventDispatcher()
    events: list[WorkflowEvent] = []
    dispatcher.subscribe(events.append)

    graph = WorkflowBuilder(nodes).build(event_dispatcher=dispatcher, run_id=RUN_ID)

    return graph, llm_service, events, dispatcher


def _sequence(events: list[WorkflowEvent]) -> list[tuple[EventType, AgentType | None]]:
    return [(event.event_type, event.agent) for event in events]


def test_full_successful_run_emits_expected_event_sequence(tmp_path: Path) -> None:
    output_directory = tmp_path / "project"
    output_directory.mkdir()

    graph, _, events, dispatcher = _build_workflow_with_events(
        developer_script=[
            _implementation_payload(
                _calc_file(WORKING_CALC_CONTENT, "Calculator module."),
                _test_file(),
            )
        ],
        tester_script=[TESTER_ANALYSIS],
        reviewer_script=[REVIEW_PASSED],
        debugger_script=[DEBUG_ANALYSIS],
        output_directory=output_directory,
    )

    result = _as_workflow_state(graph.invoke(_initial_state(output_directory)))

    assert result.execution.workflow_status == WorkflowStatus.COMPLETED
    assert all(event.run_id == RUN_ID for event in events)

    assert _sequence(events) == [
        (EventType.AGENT_STARTED, AgentType.ANALYSIS),
        (EventType.AGENT_INVOCATION_RECORDED, AgentType.ANALYSIS),
        (EventType.AGENT_COMPLETED, AgentType.ANALYSIS),
        (EventType.AGENT_STARTED, AgentType.PLANNER),
        (EventType.AGENT_INVOCATION_RECORDED, AgentType.PLANNER),
        (EventType.AGENT_COMPLETED, AgentType.PLANNER),
        (EventType.AGENT_STARTED, AgentType.ARCHITECT),
        (EventType.AGENT_INVOCATION_RECORDED, AgentType.ARCHITECT),
        (EventType.AGENT_COMPLETED, AgentType.ARCHITECT),
        (EventType.AGENT_STARTED, AgentType.DEVELOPER),
        (EventType.AGENT_INVOCATION_RECORDED, AgentType.DEVELOPER),
        (EventType.AGENT_COMPLETED, AgentType.DEVELOPER),
        (EventType.AGENT_STARTED, AgentType.STATIC_VALIDATION),
        (EventType.AGENT_INVOCATION_RECORDED, AgentType.STATIC_VALIDATION),
        (EventType.AGENT_COMPLETED, AgentType.STATIC_VALIDATION),
        (EventType.AGENT_STARTED, AgentType.TESTER),
        (EventType.AGENT_INVOCATION_RECORDED, AgentType.TESTER),
        (EventType.AGENT_COMPLETED, AgentType.TESTER),
        (EventType.TESTING_PASSED, AgentType.TESTER),
        (EventType.AGENT_STARTED, AgentType.REVIEWER),
        (EventType.AGENT_INVOCATION_RECORDED, AgentType.REVIEWER),
        (EventType.AGENT_COMPLETED, AgentType.REVIEWER),
        (EventType.REVIEW_PASSED, AgentType.REVIEWER),
        (EventType.AGENT_STARTED, AgentType.DOCUMENTATION),
        (EventType.AGENT_INVOCATION_RECORDED, AgentType.DOCUMENTATION),
        (EventType.AGENT_COMPLETED, AgentType.DOCUMENTATION),
        (EventType.DOCUMENTATION_GENERATED, AgentType.DOCUMENTATION),
    ]


def test_developer_repair_after_test_failure_emits_events_only_for_new_execution(
    tmp_path: Path,
) -> None:
    output_directory = tmp_path / "project"
    output_directory.mkdir()

    graph, _, events, dispatcher = _build_workflow_with_events(
        developer_script=[
            _implementation_payload(
                _calc_file(BROKEN_CALC_CONTENT, "Calculator module (buggy)."),
                _test_file(),
            ),
            _implementation_payload(
                _calc_file(WORKING_CALC_CONTENT, "Calculator module (fixed)."),
            ),
        ],
        tester_script=[TESTER_ANALYSIS],
        reviewer_script=[REVIEW_PASSED],
        debugger_script=[DEBUG_ANALYSIS],
        output_directory=output_directory,
    )

    result = _as_workflow_state(graph.invoke(_initial_state(output_directory)))

    assert result.execution.test_retry_count == 1
    assert result.execution.workflow_status == WorkflowStatus.COMPLETED

    developer_events = [e for e in events if e.agent == AgentType.DEVELOPER]
    tester_events = [e for e in events if e.agent == AgentType.TESTER]
    debugger_events = [e for e in events if e.agent == AgentType.DEBUGGER]

    assert len(developer_events) == 6
    assert len(tester_events) == 8
    assert len(debugger_events) == 3

    testing_outcomes = [e.event_type for e in events if e.agent == AgentType.TESTER and e.event_type in (EventType.TESTING_PASSED, EventType.TESTING_FAILED)]
    assert testing_outcomes == [EventType.TESTING_FAILED, EventType.TESTING_PASSED]


def test_developer_repair_after_review_failure_emits_events_only_for_new_execution(
    tmp_path: Path,
) -> None:
    output_directory = tmp_path / "project"
    output_directory.mkdir()

    review_failed_then_passed = [
        {
            "passed": False,
            "score": 4.0,
            "issues": [
                {
                    "title": "Missing validation",
                    "description": "Divisor is not validated before use.",
                    "severity": "high",
                    "file_path": "calc.py",
                }
            ],
            "strengths": [],
            "recommendations": ["Validate divisor before dividing."],
            "review_summary": "Needs a validation fix.",
        },
        REVIEW_PASSED,
    ]

    graph, _, events, dispatcher = _build_workflow_with_events(
        developer_script=[
            _implementation_payload(
                _calc_file(WORKING_CALC_CONTENT, "Calculator module."),
                _test_file(),
            ),
            _implementation_payload(
                _calc_file(WORKING_CALC_CONTENT, "Calculator module (revised)."),
            ),
        ],
        tester_script=[TESTER_ANALYSIS],
        reviewer_script=REVIEW_PASSED,
        review_failure_script=review_failed_then_passed,
        debugger_script=[DEBUG_ANALYSIS],
        output_directory=output_directory,
    )

    result = _as_workflow_state(graph.invoke(_initial_state(output_directory)))

    assert result.execution.review_retry_count == 1
    assert result.execution.test_retry_count == 0
    assert result.execution.workflow_status == WorkflowStatus.COMPLETED

    developer_events = [e for e in events if e.agent == AgentType.DEVELOPER]
    reviewer_events = [e for e in events if e.agent == AgentType.REVIEWER]
    debugger_events = [e for e in events if e.agent == AgentType.DEBUGGER]

    assert len(developer_events) == 6
    review_outcomes = [
        e.event_type
        for e in reviewer_events
        if e.event_type in (EventType.REVIEW_PASSED, EventType.REVIEW_FAILED)
    ]
    assert review_outcomes == [EventType.REVIEW_FAILED, EventType.REVIEW_PASSED]

    assert len(debugger_events) == 3
    debugger_invocation = next(
        e for e in debugger_events if e.event_type == EventType.AGENT_INVOCATION_RECORDED
    )
    assert debugger_invocation.metadata["repair_trigger"] == "review_feedback"


def test_event_emission_does_not_change_retry_counters_or_routing(
    tmp_path: Path,
) -> None:

    output_directory = tmp_path / "project"
    output_directory.mkdir()

    from backend.core.constants import MAX_TEST_RETRIES

    graph, _, events, dispatcher = _build_workflow_with_events(
        developer_script=[
            _implementation_payload(
                _calc_file(BROKEN_CALC_CONTENT + "\n# v1", "Calculator module 1."),
                _test_file(ALWAYS_FAILING_TEST_CONTENT),
            ),
            _implementation_payload(
                _calc_file(BROKEN_CALC_CONTENT + "\n# v2", "Calculator module 2."),
                _test_file(ALWAYS_FAILING_TEST_CONTENT),
            ),
            _implementation_payload(
                _calc_file(BROKEN_CALC_CONTENT + "\n# v3", "Calculator module 3."),
                _test_file(ALWAYS_FAILING_TEST_CONTENT),
            ),
            _implementation_payload(
                _calc_file(BROKEN_CALC_CONTENT + "\n# v4", "Calculator module 4."),
                _test_file(ALWAYS_FAILING_TEST_CONTENT),
            ),
        ],


        tester_script=[TESTER_ANALYSIS],
        reviewer_script=[REVIEW_PASSED],
        debugger_script=[DEBUG_ANALYSIS],
        output_directory=output_directory,
    )

    result = _as_workflow_state(
        graph.invoke(_initial_state(output_directory), config={"recursion_limit": 100})
    )

    assert result.execution.test_retry_count == MAX_TEST_RETRIES + 1
    assert result.execution.workflow_status == WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES
    assert result.execution.review_retry_count == 0

    reviewer_events = [e for e in events if e.agent == AgentType.REVIEWER]
    documentation_events = [e for e in events if e.agent == AgentType.DOCUMENTATION]
    assert reviewer_events == []
    assert documentation_events == []


def test_failing_event_subscriber_does_not_corrupt_workflow_state(tmp_path: Path) -> None:
    output_directory = tmp_path / "project"
    output_directory.mkdir()

    graph, _, events, dispatcher = _build_workflow_with_events(
        developer_script=[
            _implementation_payload(
                _calc_file(WORKING_CALC_CONTENT, "Calculator module."),
                _test_file(),
            )
        ],
        tester_script=[TESTER_ANALYSIS],
        reviewer_script=[REVIEW_PASSED],
        debugger_script=[DEBUG_ANALYSIS],
        output_directory=output_directory,
    )

    def bad_subscriber(event: WorkflowEvent) -> None:
        raise RuntimeError("simulated broken consumer")

    dispatcher.subscribe(bad_subscriber)

    result = _as_workflow_state(graph.invoke(_initial_state(output_directory)))

    assert result.execution.workflow_status == WorkflowStatus.COMPLETED
    assert result.testing.passed is True
    assert result.review.passed is True
    assert len(events) > 0


def test_static_validation_failure_is_recorded_as_a_failed_invocation(tmp_path: Path) -> None:

    output_directory = tmp_path / "project"
    output_directory.mkdir()

    graph, _, events, dispatcher = _build_workflow_with_events(
        developer_script=[
            _implementation_payload(_calc_file("def broken(:\n    pass", "Broken module.")),
            _implementation_payload(
                _calc_file(WORKING_CALC_CONTENT, "Calculator module (fixed)."),
                _test_file(),
            ),
        ],
        tester_script=[TESTER_ANALYSIS],
        reviewer_script=[REVIEW_PASSED],
        debugger_script=[DEBUG_ANALYSIS],
        output_directory=output_directory,
    )

    result = _as_workflow_state(graph.invoke(_initial_state(output_directory)))

    assert result.execution.workflow_status == WorkflowStatus.COMPLETED

    static_validation_invocations = [
        e
        for e in events
        if e.agent == AgentType.STATIC_VALIDATION and e.event_type == EventType.AGENT_INVOCATION_RECORDED
    ]

    assert len(static_validation_invocations) == 2
    assert static_validation_invocations[0].metadata["status"] == "failure"
    assert static_validation_invocations[0].metadata["recovery_reason"] == "pytest_failure"
    assert static_validation_invocations[0].metadata["attempt_number"] == 1
    assert static_validation_invocations[1].metadata["status"] == "success"
    assert static_validation_invocations[1].metadata["attempt_number"] == 2

    debugger_invocations = [
        e for e in events if e.agent == AgentType.DEBUGGER and e.event_type == EventType.AGENT_INVOCATION_RECORDED
    ]
    developer_invocations = [
        e for e in events if e.agent == AgentType.DEVELOPER and e.event_type == EventType.AGENT_INVOCATION_RECORDED
    ]
    assert debugger_invocations[0].metadata["repair_trigger"] == "static_validation_failure"
    assert developer_invocations[1].metadata["repair_trigger"] == "static_validation_failure"
