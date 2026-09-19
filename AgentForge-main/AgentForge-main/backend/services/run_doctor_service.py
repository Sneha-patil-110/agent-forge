
from __future__ import annotations

from typing import NamedTuple

from backend.state.execution_state import INFRASTRUCTURE_FAILURE_CATEGORIES, FailureCategory, WorkflowStatus
from backend.state.workflow_state import WorkflowState

_INFRA_STAGE_ORDER = [
    ("Static validation", {FailureCategory.STATIC_VALIDATION_ERROR}),
    ("Repository completeness", {FailureCategory.REPOSITORY_COMPLETENESS_ERROR}),
    ("Test discovery", {FailureCategory.TEST_DISCOVERY_ERROR}),
    ("Environment preflight", {FailureCategory.ENVIRONMENT_ERROR}),
    ("Dependency preparation", {FailureCategory.DEPENDENCY_INSTALL_ERROR, FailureCategory.DEPENDENCY_RESOLUTION_ERROR}),
    ("Test execution", {FailureCategory.TEST_EXECUTION_ERROR, FailureCategory.TEST_TIMEOUT}),
]


class StageResult(NamedTuple):
    label: str
    status: str


class DoctorReport(NamedTuple):
    run_id: str
    workflow_status: WorkflowStatus
    stages: list[StageResult]
    total_tests: int
    passed_tests: int
    failed_tests: int
    classification: FailureCategory | None
    repair_attempts: int
    terminal_reason: str
    error_message: str | None
    tester_summary: str | None
    debug_summary: str | None


class RunDoctorService:
    def diagnose(self, *, run_id: str, state: WorkflowState) -> DoctorReport:
        stages = self._diagnose_stages(state)

        return DoctorReport(
            run_id=run_id,
            workflow_status=state.execution.workflow_status,
            stages=stages,
            total_tests=state.testing.total_tests,
            passed_tests=state.testing.passed_tests,
            failed_tests=len(state.testing.failed_tests),
            classification=state.testing.classification,
            repair_attempts=len(state.execution.repair_history),
            terminal_reason=self._terminal_reason(state),
            error_message=state.execution.error_message,
            tester_summary=state.tester_analysis.summary,
            debug_summary=state.debug.debug_summary,
        )

    @staticmethod
    def _diagnose_stages(state: WorkflowState) -> list[StageResult]:
        stages: list[StageResult] = []

        stages.append(
            StageResult(
                "Repository generation",
                "PASS" if state.implementation.written_files else "FAIL",
            )
        )
        stages.append(
            StageResult(
                "Repository integrity",
                "PASS" if state.repository_snapshot and state.repository_snapshot.file_tree else "UNKNOWN",
            )
        )

        classification = state.testing.classification
        reached_test_pipeline = bool(state.test_plans) or classification is not None or state.testing.passed

        if not reached_test_pipeline:
            for label, _ in _INFRA_STAGE_ORDER:
                stages.append(StageResult(label, "SKIP"))
            return stages

        failed_at = next(
            (label for label, categories in _INFRA_STAGE_ORDER if classification in categories),
            None,
        )

        seen_failure = False
        for label, _ in _INFRA_STAGE_ORDER:
            if seen_failure:
                stages.append(StageResult(label, "SKIP"))
            elif label == failed_at:
                stages.append(StageResult(label, "FAIL"))
                seen_failure = True
            else:
                stages.append(StageResult(label, "PASS"))

        if not seen_failure:
            if state.testing.passed:
                stages.append(StageResult("Application tests", "PASS"))
            elif classification in {
                FailureCategory.APPLICATION_CODE_ERROR,
                FailureCategory.GENERATED_TEST_ERROR,
                FailureCategory.TEST_FAILURE,
            }:
                stages.append(StageResult("Application tests", "FAIL"))

        return stages

    @staticmethod
    def _terminal_reason(state: WorkflowState) -> str:
        status = state.execution.workflow_status
        step = (state.execution.current_step or "").lower()
        classification = state.testing.classification

        if status == WorkflowStatus.COMPLETED:
            return "VERIFIED"

        if status == WorkflowStatus.RUNNING or status == WorkflowStatus.INITIALIZED:
            return "IN_PROGRESS"

        if status == WorkflowStatus.WAITING_FOR_USER:
            return "WAITING_FOR_USER"

        if "no code changes" in step or "no_effect_repair" in step:
            return "NO_EFFECT_REPAIR"

        if classification in INFRASTRUCTURE_FAILURE_CATEGORIES:
            return "INFRASTRUCTURE_FAILURE"

        if "retry limit" in step:
            return "VERIFICATION_REPAIR_EXHAUSTED"

        if status == WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES:
            return "VERIFICATION_INCOMPLETE"

        return "GENERATION_FAILED"
