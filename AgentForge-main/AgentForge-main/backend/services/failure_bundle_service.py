
from __future__ import annotations

from backend.state.execution_state import WorkflowStatus
from backend.state.failure_bundle import FailureBundle
from backend.state.workflow_state import WorkflowState

_TERMINAL_WITH_ISSUES = (WorkflowStatus.FAILED, WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES)


class FailureBundleService:
    def should_persist(self, state: WorkflowState) -> bool:
        return state.execution.workflow_status in _TERMINAL_WITH_ISSUES

    def build(self, *, run_id: str, state: WorkflowState) -> FailureBundle:
        return FailureBundle(
            run_id=run_id,
            workflow_status=state.execution.workflow_status,
            failure_classification=state.testing.classification,
            error_message=state.execution.error_message,
            current_step=state.execution.current_step,
            current_agent=state.execution.current_agent,
            project=state.project,
            architecture=state.architecture,
            test_plans=state.test_plans,
            testing=state.testing,
            tester_analysis=state.tester_analysis,
            debug=state.debug,
            review=state.review,
            repair_history=state.execution.repair_history,
            repository_snapshot=state.repository_snapshot,
            written_files=state.implementation.written_files,
            test_retry_count=state.execution.test_retry_count,
            review_retry_count=state.execution.review_retry_count,
        )
