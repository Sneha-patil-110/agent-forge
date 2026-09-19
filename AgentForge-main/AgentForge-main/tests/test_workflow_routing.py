from __future__ import annotations

from langgraph.graph import END

from backend.core.constants import MAX_REVIEW_ATTEMPTS, MAX_REVIEW_RETRIES, MAX_TEST_RETRIES
from backend.graph.nodes import WorkflowNodes
from backend.graph.router import WorkflowRouter
from backend.state.execution_state import RepairTrigger, WorkflowStatus
from backend.state.review_state import ReviewIssue, ReviewState, Severity
from backend.state.tester_analysis import TesterAnalysis
from backend.state.workflow_state import WorkflowState
from tests.support.workflow_node_fixtures import (
    StubDependencyPreparationService,
    StubEnvironmentPreflightService,
    StubRepositoryIntegrityValidator,
    StubTestDiscoveryService,
    StubTestingService,
)


class _StubReviewerAgent:
    def __init__(self, passed: bool, *, issues: list | None = None) -> None:
        self.passed = passed
        self.issues = issues or []

    def run(self, state: WorkflowState) -> WorkflowState:
        state.review = ReviewState(
            passed=self.passed,
            score=1.0,
            issues=self.issues,
            attempt_number=state.execution.review_retry_count + 1,
        )
        return state


class _StubTesterAgent:

    def run(self, state: WorkflowState) -> WorkflowState:
        state.tester_analysis = TesterAnalysis(classification=None)
        return state


class _StubDebuggerAgent:
    def run(self, state: WorkflowState) -> WorkflowState:
        return state


def _make_nodes(
    *,
    reviewer_passed: bool | None = None,
    reviewer_issues: list | None = None,
    testing_passed: bool | None = None,
) -> WorkflowNodes:
    return WorkflowNodes(
        analysis_agent=None,
        planner_agent=None,
        architect_agent=None,
        developer_agent=None,
        tester_agent=_StubTesterAgent(),
        debugger_agent=_StubDebuggerAgent(),
        reviewer_agent=(
            _StubReviewerAgent(reviewer_passed, issues=reviewer_issues)
            if reviewer_passed is not None
            else None
        ),
        documentation_agent=None,
        materialization_service=None,
        testing_service=(
            StubTestingService(testing_passed)
            if testing_passed is not None
            else None
        ),
        repository_integrity_validator=StubRepositoryIntegrityValidator(),
        test_discovery_service=StubTestDiscoveryService(),
        environment_preflight_service=StubEnvironmentPreflightService(),
        dependency_preparation_service=StubDependencyPreparationService(),
    )


def test_review_router_routes_to_documentation_when_passed() -> None:
    state = WorkflowState()
    state.review.passed = True

    assert WorkflowRouter.review_router(state) == "documentation"


def test_review_router_routes_to_debugger_when_failed_with_retries_left() -> None:
    state = WorkflowState()
    state.review.passed = False
    state.execution.review_retry_count = 1

    assert WorkflowRouter.review_router(state) == "debugger"


def test_review_router_routes_to_end_when_workflow_marked_failed() -> None:
    state = WorkflowState()
    state.review.passed = False
    state.execution.workflow_status = WorkflowStatus.FAILED

    assert WorkflowRouter.review_router(state) == END


def test_reviewer_node_increments_review_retry_count_on_failure() -> None:
    nodes = _make_nodes(reviewer_passed=False)
    state = WorkflowState()

    state = nodes.reviewer(state)

    assert state.execution.review_retry_count == 1
    assert state.execution.test_retry_count == 0
    assert state.execution.workflow_status != WorkflowStatus.FAILED
    assert state.execution.last_repair_trigger == RepairTrigger.REVIEW_FEEDBACK


def test_reviewer_node_does_not_increment_review_retry_count_on_pass() -> None:
    nodes = _make_nodes(reviewer_passed=True)
    state = WorkflowState()

    state = nodes.reviewer(state)

    assert state.execution.review_retry_count == 0
    assert state.execution.last_repair_trigger == RepairTrigger.NONE


def test_reviewer_node_marks_failed_after_retry_limit_exceeded() -> None:
    nodes = _make_nodes(
        reviewer_passed=False,
        reviewer_issues=[ReviewIssue(title="t", description="d", severity=Severity.CRITICAL)],
    )
    state = WorkflowState()
    state.execution.review_retry_count = MAX_REVIEW_RETRIES

    state = nodes.reviewer(state)

    assert state.execution.review_retry_count == MAX_REVIEW_RETRIES + 1
    assert state.execution.workflow_status == WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES
    assert WorkflowRouter.review_router(state) == END


def test_review_retry_loop_terminates_within_bounded_attempts() -> None:

    nodes = _make_nodes(
        reviewer_passed=False,
        reviewer_issues=[ReviewIssue(title="t", description="d", severity=Severity.CRITICAL)],
    )
    state = WorkflowState()

    attempts = 0
    max_iterations = MAX_REVIEW_RETRIES + 5

    for _ in range(max_iterations):
        state = nodes.reviewer(state)
        attempts += 1

        route = WorkflowRouter.review_router(state)

        if route == END:
            break
    else:
        raise AssertionError("Review retry loop did not terminate.")

    assert attempts == MAX_REVIEW_RETRIES + 1


def test_review_retry_loop_terminates_via_auto_pass_for_non_critical_finding() -> None:

    nodes = _make_nodes(reviewer_passed=False, reviewer_issues=[])
    state = WorkflowState()

    attempts = 0
    max_iterations = MAX_REVIEW_RETRIES + 5

    for _ in range(max_iterations):
        state = nodes.reviewer(state)
        attempts += 1

        if state.review.auto_passed:
            break
    else:
        raise AssertionError("Review retry loop did not auto-pass.")

    assert attempts == MAX_REVIEW_ATTEMPTS
    assert WorkflowRouter.review_router(state) == "documentation"


def test_tester_router_routes_to_reviewer_when_passed() -> None:
    state = WorkflowState()
    state.testing.passed = True

    assert WorkflowRouter.tester_router(state) == "reviewer"


def test_tester_router_routes_to_debugger_when_failed_with_retries_left() -> None:
    state = WorkflowState()
    state.testing.passed = False
    state.execution.test_retry_count = 1

    assert WorkflowRouter.tester_router(state) == "debugger"


def test_tester_router_routes_to_end_when_workflow_marked_failed() -> None:
    state = WorkflowState()
    state.testing.passed = False
    state.execution.workflow_status = WorkflowStatus.FAILED

    assert WorkflowRouter.tester_router(state) == END


def test_tester_node_increments_test_retry_count_on_failure() -> None:
    nodes = _make_nodes(testing_passed=False)
    state = WorkflowState()

    state = nodes.tester(state)

    assert state.execution.test_retry_count == 1
    assert state.execution.review_retry_count == 0
    assert state.execution.workflow_status != WorkflowStatus.FAILED


def test_tester_node_does_not_increment_test_retry_count_on_pass() -> None:
    nodes = _make_nodes(testing_passed=True)
    state = WorkflowState()

    state = nodes.tester(state)

    assert state.execution.test_retry_count == 0
    assert state.testing.passed is True


def test_tester_node_marks_failed_after_retry_limit_exceeded() -> None:
    nodes = _make_nodes(testing_passed=False)
    state = WorkflowState()
    state.execution.test_retry_count = MAX_TEST_RETRIES

    state = nodes.tester(state)

    assert state.execution.test_retry_count == MAX_TEST_RETRIES + 1
    assert state.execution.workflow_status == WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES
    assert WorkflowRouter.tester_router(state) == END


def test_debugger_node_sets_repair_trigger_to_test_failure() -> None:
    nodes = _make_nodes()
    state = WorkflowState()

    state = nodes.debugger(state)

    assert state.execution.last_repair_trigger == RepairTrigger.TEST_FAILURE


def test_debugger_node_does_not_change_test_retry_count() -> None:
    nodes = _make_nodes()
    state = WorkflowState()
    state.execution.test_retry_count = 2

    state = nodes.debugger(state)

    assert state.execution.test_retry_count == 2


def test_test_retry_loop_terminates_within_bounded_attempts() -> None:

    nodes = _make_nodes(testing_passed=False)
    state = WorkflowState()

    attempts = 0
    max_iterations = MAX_TEST_RETRIES + 5

    for _ in range(max_iterations):
        state = nodes.tester(state)
        attempts += 1

        route = WorkflowRouter.tester_router(state)

        if route == END:
            break
    else:
        raise AssertionError("Test retry loop did not terminate.")

    assert attempts == MAX_TEST_RETRIES + 1


def test_test_and_review_retry_counters_are_independent() -> None:

    nodes = _make_nodes(testing_passed=False, reviewer_passed=False)
    state = WorkflowState()

    state = nodes.tester(state)
    assert state.execution.test_retry_count == 1
    assert state.execution.review_retry_count == 0

    state = nodes.reviewer(state)
    assert state.execution.review_retry_count == 1
    assert state.execution.test_retry_count == 1
