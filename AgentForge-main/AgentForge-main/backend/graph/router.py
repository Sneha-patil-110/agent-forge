
from __future__ import annotations

from langgraph.graph import END

from backend.graph.workflow import WorkflowNode
from backend.state.execution_state import WorkflowStatus
from backend.state.workflow_state import WorkflowState

_TERMINAL_STATUSES = (WorkflowStatus.FAILED, WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES)


class WorkflowRouter:
    @staticmethod
    def static_validation_router(
        state: WorkflowState,
    ) -> str:
        if state.testing.passed:
            return WorkflowNode.TESTER.value

        if state.execution.workflow_status in _TERMINAL_STATUSES:
            return END

        return WorkflowNode.DEBUGGER.value

    @staticmethod
    def tester_router(
        state: WorkflowState,
    ) -> str:
        if state.testing.passed:
            return WorkflowNode.REVIEWER.value

        if state.execution.workflow_status in _TERMINAL_STATUSES:
            return END

        return WorkflowNode.DEBUGGER.value

    @staticmethod
    def review_router(
        state: WorkflowState,
    ) -> str:
        if state.review.passed or state.review.auto_passed:
            return WorkflowNode.DOCUMENTATION.value

        if state.execution.workflow_status in _TERMINAL_STATUSES:
            return END

        return WorkflowNode.DEBUGGER.value
