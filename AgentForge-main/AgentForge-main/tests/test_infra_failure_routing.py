
from __future__ import annotations

import pytest
from langgraph.graph import END

from backend.core.exceptions import AgentOutputSchemaError
from backend.graph.nodes import WorkflowNodes
from backend.graph.router import WorkflowRouter
from backend.services.dependency_preparation_service import DependencyPreparationResult
from backend.services.environment_preflight_service import PreflightIssue, PreflightResult
from backend.state.execution_state import FailureCategory, WorkflowStatus
from backend.state.project_state import ProjectState
from backend.state.test_plan import TestPlan, TestStage
from backend.state.tester_analysis import TesterAnalysis
from backend.state.testing_state import TestingState, TestStatus
from backend.state.workflow_state import WorkflowState
from tests.support.workflow_node_fixtures import (
    StubRepositoryIntegrityValidator,
    make_stub_test_plan,
)


class _RecordingTesterAgent:

    def __init__(self) -> None:
        self.calls = 0

    def run(self, state: WorkflowState) -> WorkflowState:
        self.calls += 1
        analysis = TesterAnalysis(classification=FailureCategory.APPLICATION_CODE_ERROR)
        state.tester_analysis = analysis
        if state.testing.classification is None:
            state.testing.classification = analysis.classification
        return state


class _RecordingDebuggerAgent:
    def __init__(self) -> None:
        self.calls = 0
        self.received_tester_analysis: TesterAnalysis | None = None

    def run(self, state: WorkflowState) -> WorkflowState:
        self.calls += 1
        self.received_tester_analysis = state.tester_analysis
        return state


class _EmptyDiscoveryService:
    def discover(self, snapshot):
        return []


class _FailingPreflightService:
    def check(self, *, project_root, integrity_passed, plan):
        return PreflightResult(passed=False, issues=[PreflightIssue("RUNTIME_UNAVAILABLE", "node is not available.")])


class _FailingDependencyService:
    def __init__(self, *, failure_kind=None) -> None:
        from backend.services.pip_failure_classifier import PipFailureKind

        self.failure_kind = failure_kind or PipFailureKind.TRANSIENT

    def prepare(self, *, project_root, plan):
        return DependencyPreparationResult(
            working_directory=plan.working_directory,
            success=False,
            error_message="pip install failed: no matching distribution.",
            failure_kind=self.failure_kind,
        )


class _RejectingTestingService:

    def execute_stage(self, *, project, plan, stage, attempt_number, targeted_tests=None) -> TestingState:
        return TestingState(
            status=TestStatus.ERROR,
            error_type="process_error",
            attempt_number=attempt_number,
            testing_summary="Test process could not start.",
        )


class _TimeoutTestingService:
    def execute_stage(self, *, project, plan, stage, attempt_number, targeted_tests=None) -> TestingState:
        return TestingState(
            status=TestStatus.TIMEOUT,
            timed_out=True,
            attempt_number=attempt_number,
            testing_summary="Test process timed out.",
        )


class _RealFailureTestingService:

    def execute_stage(self, *, project, plan, stage, attempt_number, targeted_tests=None) -> TestingState:
        from backend.state.testing_state import TestFailure

        return TestingState(
            status=TestStatus.FAILED,
            command=stage.command,
            exit_code=1,
            passed=False,
            attempt_number=attempt_number,
            failed_tests=[TestFailure(name="test_x", message="assertion failed")],
        )


def _state_with_project() -> WorkflowState:
    state = WorkflowState()
    state.project = ProjectState(output_directory="workspace/proj_stub")
    return state


def _nodes(**kwargs) -> WorkflowNodes:
    defaults = dict(
        analysis_agent=None,
        planner_agent=None,
        architect_agent=None,
        developer_agent=None,
        debugger_agent=_RecordingDebuggerAgent(),
        reviewer_agent=None,
        documentation_agent=None,
        materialization_service=None,
        repository_integrity_validator=StubRepositoryIntegrityValidator(),
        environment_preflight_service=type("P", (), {"check": staticmethod(
            lambda **kw: PreflightResult(passed=True, issues=[])
        )})(),
        dependency_preparation_service=None,
    )
    defaults.update(kwargs)
    return WorkflowNodes(**defaults)


def test_discovery_failure_never_reaches_debugger() -> None:
    debugger = _RecordingDebuggerAgent()
    tester_agent = _RecordingTesterAgent()
    nodes = _nodes(
        debugger_agent=debugger,
        tester_agent=tester_agent,
        test_discovery_service=_EmptyDiscoveryService(),
        testing_service=None,
    )
    state = _state_with_project()

    result = nodes.tester(state)

    assert result.testing.classification == FailureCategory.TEST_DISCOVERY_ERROR
    assert tester_agent.calls == 0
    assert result.execution.workflow_status == WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES
    assert WorkflowRouter.tester_router(result) == END
    assert debugger.calls == 0


def test_environment_failure_never_reaches_debugger() -> None:
    debugger = _RecordingDebuggerAgent()
    tester_agent = _RecordingTesterAgent()
    nodes = _nodes(
        debugger_agent=debugger,
        tester_agent=tester_agent,
        test_discovery_service=type("D", (), {"discover": staticmethod(lambda snapshot: [make_stub_test_plan()])})(),
        environment_preflight_service=_FailingPreflightService(),
        testing_service=None,
    )
    state = _state_with_project()

    result = nodes.tester(state)

    assert result.testing.classification == FailureCategory.ENVIRONMENT_ERROR
    assert tester_agent.calls == 0
    assert debugger.calls == 0
    assert result.execution.workflow_status == WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES


def test_transient_dependency_install_failure_never_reaches_debugger() -> None:

    from backend.services.pip_failure_classifier import PipFailureKind

    debugger = _RecordingDebuggerAgent()
    tester_agent = _RecordingTesterAgent()
    nodes = _nodes(
        debugger_agent=debugger,
        tester_agent=tester_agent,
        test_discovery_service=type("D", (), {"discover": staticmethod(lambda snapshot: [make_stub_test_plan()])})(),
        dependency_preparation_service=_FailingDependencyService(failure_kind=PipFailureKind.TRANSIENT),
        testing_service=None,
    )
    state = _state_with_project()

    result = nodes.tester(state)

    assert result.testing.classification == FailureCategory.DEPENDENCY_INSTALL_ERROR
    assert tester_agent.calls == 0
    assert debugger.calls == 0
    assert result.execution.workflow_status == WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES


def test_genuine_dependency_resolution_failure_routes_to_debugger() -> None:

    from backend.services.pip_failure_classifier import PipFailureKind

    debugger = _RecordingDebuggerAgent()
    tester_agent = _RecordingTesterAgent()
    nodes = _nodes(
        debugger_agent=debugger,
        tester_agent=tester_agent,
        test_discovery_service=type("D", (), {"discover": staticmethod(lambda snapshot: [make_stub_test_plan()])})(),
        dependency_preparation_service=_FailingDependencyService(failure_kind=PipFailureKind.DEPENDENCY_ERROR),
        testing_service=None,
    )
    state = _state_with_project()

    result = nodes.tester(state)

    assert result.testing.classification == FailureCategory.DEPENDENCY_RESOLUTION_ERROR
    assert result.testing.classification != FailureCategory.DEPENDENCY_INSTALL_ERROR
    assert tester_agent.calls == 0
    assert debugger.calls == 0
    assert result.execution.workflow_status != WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES
    assert result.execution.dependency_retry_count == 1
    assert result.execution.test_retry_count == 0
    assert WorkflowRouter.tester_router(result) == "debugger"


def test_test_process_error_never_reaches_debugger() -> None:
    debugger = _RecordingDebuggerAgent()
    tester_agent = _RecordingTesterAgent()
    nodes = _nodes(
        debugger_agent=debugger,
        tester_agent=tester_agent,
        test_discovery_service=type("D", (), {"discover": staticmethod(lambda snapshot: [make_stub_test_plan()])})(),
        testing_service=_RejectingTestingService(),
    )
    state = _state_with_project()

    result = nodes.tester(state)

    assert result.testing.classification == FailureCategory.TEST_EXECUTION_ERROR
    assert tester_agent.calls == 0
    assert debugger.calls == 0


def test_test_timeout_never_reaches_debugger() -> None:
    debugger = _RecordingDebuggerAgent()
    tester_agent = _RecordingTesterAgent()
    nodes = _nodes(
        debugger_agent=debugger,
        tester_agent=tester_agent,
        test_discovery_service=type("D", (), {"discover": staticmethod(lambda snapshot: [make_stub_test_plan()])})(),
        testing_service=_TimeoutTestingService(),
    )
    state = _state_with_project()

    result = nodes.tester(state)

    assert result.testing.classification == FailureCategory.TEST_TIMEOUT
    assert tester_agent.calls == 0
    assert debugger.calls == 0


def test_genuine_test_failure_does_reach_tester_and_debugger() -> None:

    debugger = _RecordingDebuggerAgent()
    tester_agent = _RecordingTesterAgent()
    nodes = _nodes(
        debugger_agent=debugger,
        tester_agent=tester_agent,
        test_discovery_service=type("D", (), {"discover": staticmethod(lambda snapshot: [make_stub_test_plan()])})(),
        testing_service=_RealFailureTestingService(),
    )
    state = _state_with_project()

    result = nodes.tester(state)

    assert tester_agent.calls == 1
    assert result.testing.classification == FailureCategory.APPLICATION_CODE_ERROR
    assert WorkflowRouter.tester_router(result) == "debugger"


def test_malformed_tester_output_is_not_treated_as_a_test_failure() -> None:

    class _BrokenTesterAgent:
        def run(self, state: WorkflowState) -> WorkflowState:
            raise AgentOutputSchemaError("Tester Agent output does not match the expected analysis schema.")

    debugger = _RecordingDebuggerAgent()
    nodes = _nodes(
        debugger_agent=debugger,
        tester_agent=_BrokenTesterAgent(),
        test_discovery_service=type("D", (), {"discover": staticmethod(lambda snapshot: [make_stub_test_plan()])})(),
        testing_service=_RealFailureTestingService(),
    )
    state = _state_with_project()

    with pytest.raises(AgentOutputSchemaError):
        nodes.tester(state)

    assert debugger.calls == 0


def test_generated_test_error_biases_debugger_toward_the_test_file() -> None:

    debugger = _RecordingDebuggerAgent()
    tester_agent = _RecordingTesterAgent()

    class _GeneratedTestErrorTesterAgent:
        def run(self, state: WorkflowState) -> WorkflowState:
            analysis = TesterAnalysis(
                classification=FailureCategory.GENERATED_TEST_ERROR,
                affected_files=["test_x.py"],
                evidence="Architecture specifies 201; implementation returns 201; test asserts 200.",
            )
            state.tester_analysis = analysis
            state.testing.classification = analysis.classification
            return state

    nodes = _nodes(
        debugger_agent=debugger,
        tester_agent=_GeneratedTestErrorTesterAgent(),
        test_discovery_service=type("D", (), {"discover": staticmethod(lambda snapshot: [make_stub_test_plan()])})(),
        testing_service=_RealFailureTestingService(),
    )
    state = _state_with_project()

    result = nodes.tester(state)
    result = nodes.debugger(result)

    assert result.tester_analysis.classification == FailureCategory.GENERATED_TEST_ERROR
    assert result.tester_analysis.affected_files == ["test_x.py"]
    assert debugger.received_tester_analysis is not None
    assert debugger.received_tester_analysis.classification == FailureCategory.GENERATED_TEST_ERROR


class _CapturingTestingService:

    def __init__(self) -> None:
        self.received_targeted_tests: list[str] | None = "not_called"

    def execute_stage(self, *, project, plan, stage, attempt_number, targeted_tests=None) -> TestingState:
        from backend.state.testing_state import TestFailure

        self.received_targeted_tests = targeted_tests
        return TestingState(
            status=TestStatus.FAILED,
            command=stage.command,
            exit_code=1,
            passed=False,
            attempt_number=attempt_number,
            failed_tests=[TestFailure(name="test_x", message="assertion failed")],
        )


def test_targeted_retest_ignores_stale_static_validation_failure_names() -> None:

    from backend.state.testing_state import TestFailure

    testing_service = _CapturingTestingService()
    nodes = _nodes(
        debugger_agent=_RecordingDebuggerAgent(),
        tester_agent=_RecordingTesterAgent(),
        test_discovery_service=type("D", (), {"discover": staticmethod(lambda snapshot: [make_stub_test_plan()])})(),
        testing_service=testing_service,
    )
    state = _state_with_project()
    state.testing.classification = FailureCategory.STATIC_VALIDATION_ERROR
    state.testing.failed_tests = [
        TestFailure(name="backend/app/main.py:12", message="Syntax error"),
    ]

    nodes.tester(state)

    assert testing_service.received_targeted_tests is None


def test_targeted_retest_reuses_genuine_prior_test_failure_names() -> None:
    from backend.state.testing_state import TestFailure

    testing_service = _CapturingTestingService()
    nodes = _nodes(
        debugger_agent=_RecordingDebuggerAgent(),
        tester_agent=_RecordingTesterAgent(),
        test_discovery_service=type("D", (), {"discover": staticmethod(lambda snapshot: [make_stub_test_plan()])})(),
        testing_service=testing_service,
    )
    state = _state_with_project()
    state.testing.classification = FailureCategory.APPLICATION_CODE_ERROR
    state.testing.failed_tests = [
        TestFailure(name="test_calc.py::test_divide_by_zero", message="ZeroDivisionError"),
    ]

    nodes.tester(state)

    assert testing_service.received_targeted_tests == ["test_calc.py::test_divide_by_zero"]
