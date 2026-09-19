
from __future__ import annotations

import logging
from pathlib import Path


from backend.agents.analysis_agent import AnalysisAgent
from backend.agents.architect_agent import ArchitectAgent
from backend.agents.debugger_agent import DebuggerAgent
from backend.agents.developer_agent import DeveloperAgent
from backend.agents.documenter_agent import DocumentationAgent
from backend.agents.planner_agent import PlannerAgent
from backend.agents.reviewer_agent import ReviewerAgent
from backend.agents.tester_agent import TesterAgent
from backend.core.constants import (
    MAX_DEPENDENCY_RESOLUTION_RETRIES,
    MAX_REVIEW_ATTEMPTS,
    MAX_REVIEW_RETRIES,
    MAX_TEST_RETRIES,
)
from backend.services.dependency_preparation_service import (
    DependencyPreparationResult,
    DependencyPreparationService,
)
from backend.services.documentation_prefetch_service import DocumentationPrefetchService
from backend.services.environment_preflight_service import EnvironmentPreflightService
from backend.services.knowledge_manager import KnowledgeManager
from backend.events.dispatcher import EventDispatcher
from backend.events.event_types import EventType, WorkflowEvent
from backend.services.pip_failure_classifier import PipFailureKind
from backend.services.repository_completeness_service import (
    CompletenessResult,
    RepositoryCompletenessService,
)
from backend.services.repository_integrity_validator import RepositoryIntegrityValidator
from backend.services.static_validation_service import StaticValidationService
from backend.services.test_discovery_service import TestDiscoveryService
from backend.services.testing_service import TestingService
from backend.state.execution_state import (
    INFRASTRUCTURE_FAILURE_CATEGORIES,
    AgentType,
    FailureCategory,
    RepairTrigger,
    WorkflowStatus,
)
from backend.state.knowledge_state import KnowledgeCategory
from backend.state.review_state import Severity
from backend.state.test_plan import TestPlan
from backend.state.testing_state import DiscoveryStatus, TestFailure, TestingState, TestStatus
from backend.state.workflow_state import WorkflowState


logger = logging.getLogger(__name__)


class WorkflowNodes:
    def __init__(
        self,
        analysis_agent: AnalysisAgent,
        planner_agent: PlannerAgent,
        architect_agent: ArchitectAgent,
        developer_agent: DeveloperAgent,
        tester_agent: TesterAgent,
        debugger_agent: DebuggerAgent,
        reviewer_agent: ReviewerAgent,
        documentation_agent: DocumentationAgent,
        materialization_service: MaterializationService,
        testing_service: TestingService,
        knowledge_manager: KnowledgeManager | None = None,
        static_validation_service: StaticValidationService | None = None,
        documentation_prefetch_service: DocumentationPrefetchService | None = None,
        repository_integrity_validator: RepositoryIntegrityValidator | None = None,
        test_discovery_service: TestDiscoveryService | None = None,
        environment_preflight_service: EnvironmentPreflightService | None = None,
        dependency_preparation_service: DependencyPreparationService | None = None,
        repository_completeness_service: RepositoryCompletenessService | None = None,
        event_dispatcher: EventDispatcher | None = None,
    ) -> None:

        self.analysis_agent = analysis_agent
        self.planner_agent = planner_agent
        self.architect_agent = architect_agent
        self.developer_agent = developer_agent
        self.tester_agent = tester_agent
        self.debugger_agent = debugger_agent
        self.reviewer_agent = reviewer_agent
        self.documentation_agent = documentation_agent
        self.materialization_service = materialization_service
        self.testing_service = testing_service
        self.knowledge_manager = knowledge_manager or KnowledgeManager()
        self.static_validation_service = static_validation_service or StaticValidationService()
        self.documentation_prefetch_service = documentation_prefetch_service or DocumentationPrefetchService(
            mcp_executor=None, mcp_registry=None
        )
        self.repository_integrity_validator = repository_integrity_validator or RepositoryIntegrityValidator()
        self.test_discovery_service = test_discovery_service or TestDiscoveryService()
        self.environment_preflight_service = environment_preflight_service or EnvironmentPreflightService()
        self.dependency_preparation_service = dependency_preparation_service
        self.repository_completeness_service = repository_completeness_service or RepositoryCompletenessService()
        self.event_dispatcher = event_dispatcher


    def analysis(
        self,
        state: WorkflowState,
    ) -> WorkflowState:
        logger.info("Workflow started")

        return self.analysis_agent.run(state)

    def planner(
        self,
        state: WorkflowState,
    ) -> WorkflowState:
        return self.planner_agent.run(state)

    def architect(
        self,
        state: WorkflowState,
    ) -> WorkflowState:
        return self.architect_agent.run(state)

    def developer(
        self,
        state: WorkflowState,
    ) -> WorkflowState:
        previous_written_files = list(
            state.implementation.written_files
        )
        before_code = list(state.implementation.generated_code)

        self.documentation_prefetch_service.ensure_cached(state)

        state = self.developer_agent.run(state)

        state.implementation = self.materialization_service.materialize(
            project=state.project,
            implementation=state.implementation,
            previous_written_files=previous_written_files,
        )

        project_id = Path(state.project.output_directory).name if state.project.output_directory else "unknown"
        run_id = getattr(state.execution, "run_id", None) or project_id



        snapshot = self.repository_integrity_validator.create_snapshot(
            state.project.output_directory or "",
            state=state,
        )
        state.repository_snapshot = snapshot

        event_meta = {
            "project_id": project_id,
            "manifest_file_count": len(state.implementation.generated_code),
            "disk_file_count": len(snapshot.file_tree),
            "top_level_directories": snapshot.top_level_directories,
        }

        if self.event_dispatcher:
            self.event_dispatcher.emit(WorkflowEvent(
                event_type=EventType.REPOSITORY_MATERIALIZED,
                run_id=run_id,
                agent=AgentType.DEVELOPER,
                metadata=event_meta,
            ))
            self.event_dispatcher.emit(WorkflowEvent(
                event_type=EventType.REPOSITORY_INTEGRITY_STARTED,
                run_id=run_id,
                agent=AgentType.DEVELOPER,
                metadata=event_meta,
            ))

        integrity_res = self.repository_integrity_validator.validate_repository(
            state.project.output_directory,
            state=state,
            written_files=state.implementation.written_files,
        )

        if self.event_dispatcher:
            evt_type = EventType.REPOSITORY_INTEGRITY_PASSED if integrity_res.is_valid else EventType.REPOSITORY_INTEGRITY_FAILED
            self.event_dispatcher.emit(WorkflowEvent(
                event_type=evt_type,
                run_id=run_id,
                agent=AgentType.DEVELOPER,
                metadata={**event_meta, "issues": [i._asdict() for i in integrity_res.issues]},
            ))
            self.event_dispatcher.emit(WorkflowEvent(
                event_type=EventType.REPOSITORY_SNAPSHOT_CREATED,
                run_id=run_id,
                agent=AgentType.DEVELOPER,
                metadata=event_meta,
            ))

        if not integrity_res.is_valid:
            logger.error("Repository integrity validation failed: %s", integrity_res.issues)

        from backend.services.artifact_diff import compute_artifact_diff
        diff = compute_artifact_diff(before_code, state.implementation.generated_code)

        if state.execution.last_repair_trigger != RepairTrigger.NONE:
            from backend.state.repair_history import RepairAttemptRecord
            from backend.services.failure_fingerprint import compute_failure_fingerprint

            fingerprint = compute_failure_fingerprint(state.testing, state.execution.error_message)
            record = RepairAttemptRecord(
                attempt_number=state.execution.test_retry_count + 1,
                failure_fingerprint=fingerprint,
                failure_category=getattr(state.execution, "last_repair_trigger", "test_failure"),
                debugger_diagnosis=state.debug.root_cause,
                files_targeted=state.debug.affected_files,
                files_changed=diff.added_files + diff.modified_files,
                is_no_effect_repair=diff.is_no_effect,
            )
            state.execution.repair_history.append(record.model_dump())

        return state


    def static_validation(
        self,
        state: WorkflowState,
    ) -> WorkflowState:

        state.execution.current_agent = AgentType.STATIC_VALIDATION
        state.execution.current_step = "Running static validation"

        result = self.static_validation_service.validate(state.implementation.generated_code)

        if result.passed:
            state.testing = TestingState(passed=True, status=TestStatus.NOT_RUN)
            return state

        attempt_number = state.execution.test_retry_count + 1

        state.testing = TestingState(
            status=TestStatus.FAILED,
            passed=False,
            classification=FailureCategory.STATIC_VALIDATION_ERROR,
            stdout="\n".join(
                f"{issue.file}:{issue.line or '?'}: {issue.message}" for issue in result.issues
            ),
            failed_tests=[
                TestFailure(
                    name=f"{issue.file}:{issue.line or '?'}",
                    message=issue.message,
                    file_path=issue.file,
                )
                for issue in result.issues
            ],
            attempt_number=attempt_number,
            testing_summary="Static validation failed before running the real test suite.",
        )

        state.execution.last_repair_trigger = RepairTrigger.STATIC_VALIDATION_FAILURE
        state.execution.test_retry_count += 1

        if state.execution.test_retry_count > MAX_TEST_RETRIES:
            state.execution.workflow_status = WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES
            state.execution.current_step = "Static validation retry limit exceeded"
            state.execution.error_message = (
                "Static validation kept failing after the maximum number of "
                f"retries ({MAX_TEST_RETRIES})."
            )
            logger.error(
                "Static validation retry limit reached after %d attempts; "
                "verification incomplete, repository preserved",
                MAX_TEST_RETRIES,
            )
        else:
            logger.warning(
                "Static validation failed (attempt %d); routing to debugger (%d/%d)",
                attempt_number,
                state.execution.test_retry_count,
                MAX_TEST_RETRIES,
            )

        return state

    def tester(
        self,
        state: WorkflowState,
    ) -> WorkflowState:

        state.execution.current_agent = AgentType.TESTER
        state.execution.current_step = "Discovering test plan"

        attempt_number = state.execution.test_retry_count + 1

        snapshot = state.repository_snapshot or self.repository_integrity_validator.create_snapshot(
            state.project.output_directory or "", state=state
        )
        state.repository_snapshot = snapshot

        completeness = self.repository_completeness_service.check(
            project=state.project,
            architecture=state.architecture,
            snapshot=snapshot,
        )

        if not completeness.is_complete:
            return self._completeness_failure(
                state, attempt_number=attempt_number, result=completeness
            )

        plans = self.test_discovery_service.discover(snapshot)
        state.test_plans = plans

        if not plans:
            return self._infra_failure(
                state,
                attempt_number=attempt_number,
                classification=FailureCategory.TEST_DISCOVERY_ERROR,
                summary=self._describe_discovery_failure(snapshot),
                discovery_status=DiscoveryStatus.NOT_RECOGNIZED,
            )

        integrity_res = self.repository_integrity_validator.validate_repository(
            state.project.output_directory,
            state=state,
            written_files=state.implementation.written_files,
        )

        _GENUINE_TEST_FAILURE_CATEGORIES = {
            FailureCategory.APPLICATION_CODE_ERROR,
            FailureCategory.GENERATED_TEST_ERROR,
            FailureCategory.TEST_FAILURE,
        }
        targeted_tests = (
            [f.name for f in state.testing.failed_tests]
            if state.testing.failed_tests
            and state.testing.classification in _GENUINE_TEST_FAILURE_CATEGORIES
            else None
        )
        aggregated: TestingState | None = None
        tests_discovered_any = any(plan.test_files for plan in plans)
        full_suite_ran = False
        verification_methods: list[str] = []

        for plan in plans:
            preflight = self.environment_preflight_service.check(
                project_root=state.project.output_directory or "",
                integrity_passed=integrity_res.is_valid,
                plan=plan,
            )

            if not preflight.passed:
                return self._infra_failure(
                    state,
                    attempt_number=attempt_number,
                    classification=FailureCategory.ENVIRONMENT_ERROR,
                    summary="; ".join(issue.message for issue in preflight.issues),
                )

            if self.dependency_preparation_service is not None:
                dep_result = self.dependency_preparation_service.prepare(
                    project_root=state.project.output_directory or "",
                    plan=plan,
                )

                if not dep_result.success and not dep_result.skipped:
                    if dep_result.failure_kind == PipFailureKind.TRANSIENT:
                        return self._infra_failure(
                            state,
                            attempt_number=attempt_number,
                            classification=FailureCategory.DEPENDENCY_INSTALL_ERROR,
                            summary=dep_result.error_message or "Dependency installation failed.",
                            stdout=dep_result.stdout,
                            stderr=dep_result.stderr,
                        )

                    return self._dependency_resolution_failure(
                        state, attempt_number=attempt_number, result=dep_result
                    )

            plan_result: TestingState | None = None
            plan_ran_full_suite = False

            for stage in plan.stages:
                plan_result = self.testing_service.execute_stage(
                    project=state.project,
                    plan=plan,
                    stage=stage,
                    attempt_number=attempt_number,
                    targeted_tests=targeted_tests if stage.name == "full_suite" else None,
                )

                if stage.name == "full_suite":
                    plan_ran_full_suite = True
                    full_suite_ran = True

                if plan_result.status in (TestStatus.ERROR, TestStatus.TIMEOUT) or plan_result.timed_out:
                    category = (
                        FailureCategory.TEST_TIMEOUT
                        if plan_result.timed_out or plan_result.status == TestStatus.TIMEOUT
                        else FailureCategory.TEST_EXECUTION_ERROR
                    )
                    return self._infra_failure(
                        state,
                        attempt_number=attempt_number,
                        classification=category,
                        summary=plan_result.testing_summary or "Test process could not run to completion.",
                        stdout=plan_result.stdout,
                        stderr=plan_result.stderr,
                    )

                if not plan_result.passed:
                    break

            if plan_ran_full_suite:
                verification_methods.append(plan.framework)
            elif plan.stages:
                verification_methods.append(plan.stages[-1].name)
            else:
                verification_methods.append("none")

            aggregated = self._merge_testing_state(aggregated, plan_result, attempt_number)

            if not aggregated.passed:
                break

        state.testing = aggregated

        state.testing.tests_discovered = tests_discovered_any
        state.testing.tests_executed = full_suite_ran
        state.testing.verification_method = (
            "+".join(dict.fromkeys(verification_methods)) if verification_methods else "none"
        )
        state.testing.discovery_status = (
            DiscoveryStatus.RECOGNIZED_TESTABLE
            if full_suite_ran
            else DiscoveryStatus.RECOGNIZED_NO_TESTS
        )

        for failure in state.testing.failed_tests:
            self.knowledge_manager.record(
                state,
                category=KnowledgeCategory.KNOWN_LIMITATION,
                title=failure.name,
                content=failure.message or "Test failed with no captured message.",
                created_by="tester",
                source_id=failure.name,
            )

        if state.testing.passed:
            logger.info("Testing passed (attempt %d)", attempt_number)
            return state

        state = self.tester_agent.run(state)

        if state.testing.classification is None:
            state.testing.classification = FailureCategory.TEST_FAILURE

        from backend.services.failure_fingerprint import compute_failure_fingerprint
        fingerprint = compute_failure_fingerprint(state.testing)

        if state.execution.repair_history:
            last_record = state.execution.repair_history[-1]
            if (
                last_record.get("failure_fingerprint") == fingerprint
                and last_record.get("is_no_effect_repair")
            ):
                state.execution.workflow_status = WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES
                state.execution.current_step = "Identical test failure persisted with no code changes"
                state.execution.error_message = (
                    f"Test repair loop stopped: Developer repair produced no code changes for persistent failure '{fingerprint}'."
                )
                logger.error(state.execution.error_message)
                return state

        state.execution.test_retry_count += 1

        if state.execution.test_retry_count > MAX_TEST_RETRIES:
            state.execution.workflow_status = WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES
            state.execution.current_step = (
                "Test retry limit exceeded"
            )
            state.execution.error_message = (
                "Testing failed after the maximum number of retries "
                f"({MAX_TEST_RETRIES})."
            )
            logger.error(
                "Test retry limit reached after %d attempts; "
                "verification incomplete, repository preserved",
                MAX_TEST_RETRIES,
            )
        else:
            logger.warning(
                "Testing failed (attempt %d); routing to debugger (%d/%d)",
                attempt_number,
                state.execution.test_retry_count,
                MAX_TEST_RETRIES,
            )

        return state

    def _infra_failure(
        self,
        state: WorkflowState,
        *,
        attempt_number: int,
        classification: FailureCategory,
        summary: str,
        stdout: str = "",
        stderr: str = "",
        discovery_status: DiscoveryStatus | None = None,
    ) -> WorkflowState:

        assert classification in INFRASTRUCTURE_FAILURE_CATEGORIES

        state.testing = TestingState(
            status=TestStatus.ERROR,
            passed=False,
            classification=classification,
            stdout=stdout,
            stderr=stderr,
            attempt_number=attempt_number,
            testing_summary=summary,
            discovery_status=discovery_status,
        )
        state.execution.workflow_status = WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES
        state.execution.current_step = f"Test infrastructure failure: {classification.value}"
        state.execution.error_message = summary

        logger.error("Test infrastructure failure (%s): %s", classification.value, summary)

        return state

    def _completeness_failure(
        self,
        state: WorkflowState,
        *,
        attempt_number: int,
        result: CompletenessResult,
    ) -> WorkflowState:

        summary = "; ".join(issue.message for issue in result.issues)

        state.testing = TestingState(
            status=TestStatus.ERROR,
            passed=False,
            classification=FailureCategory.REPOSITORY_COMPLETENESS_ERROR,
            attempt_number=attempt_number,
            testing_summary=summary,
        )
        state.execution.last_repair_trigger = RepairTrigger.REPOSITORY_COMPLETENESS_FAILURE
        state.execution.test_retry_count += 1

        if state.execution.test_retry_count > MAX_TEST_RETRIES:
            state.execution.workflow_status = WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES
            state.execution.current_step = "Repository completeness retry limit exceeded"
            state.execution.error_message = (
                "Repository remained incomplete after the maximum number of "
                f"retries ({MAX_TEST_RETRIES}): {summary}"
            )
            logger.error(state.execution.error_message)
        else:
            state.execution.current_step = "Repository incomplete; requesting repair"
            logger.warning(
                "Repository completeness check failed (attempt %d); "
                "routing to debugger (%d/%d): %s",
                attempt_number,
                state.execution.test_retry_count,
                MAX_TEST_RETRIES,
                summary,
            )

        return state

    def _dependency_resolution_failure(
        self,
        state: WorkflowState,
        *,
        attempt_number: int,
        result: DependencyPreparationResult,
    ) -> WorkflowState:

        summary = result.error_message or "Dependency installation failed."

        if result.failure_kind == PipFailureKind.PYTHON_INCOMPATIBLE:
            summary = f"Possible Python version incompatibility: {summary}"

        state.testing = TestingState(
            status=TestStatus.ERROR,
            passed=False,
            classification=FailureCategory.DEPENDENCY_RESOLUTION_ERROR,
            command=result.command,
            stdout=result.stdout,
            stderr=result.stderr,
            attempt_number=attempt_number,
            testing_summary=summary,
        )
        state.execution.last_repair_trigger = RepairTrigger.DEPENDENCY_RESOLUTION_FAILURE
        state.execution.dependency_retry_count += 1

        if state.execution.dependency_retry_count > MAX_DEPENDENCY_RESOLUTION_RETRIES:
            state.execution.workflow_status = WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES
            state.execution.current_step = "Dependency resolution retry limit exceeded"
            state.execution.error_message = (
                "Dependency installation kept failing after the maximum "
                f"number of retries ({MAX_DEPENDENCY_RESOLUTION_RETRIES}): {summary}"
            )
            logger.error(state.execution.error_message)
        else:
            state.execution.current_step = "Dependency resolution failed; requesting repair"
            logger.warning(
                "Dependency resolution failed (attempt %d); routing to debugger (%d/%d): %s",
                attempt_number,
                state.execution.dependency_retry_count,
                MAX_DEPENDENCY_RESOLUTION_RETRIES,
                summary,
            )

        return state

    @staticmethod
    def _describe_discovery_failure(snapshot) -> str:

        file_tree = snapshot.file_tree

        if not file_tree:
            return (
                "No supported project type could be identified from the "
                "materialized repository: it contains no files."
            )

        extensions = sorted({Path(f).suffix for f in file_tree if Path(f).suffix})
        ext_desc = ", ".join(extensions) if extensions else "no recognizable file extensions"

        return (
            f"No supported project type could be identified from the "
            f"materialized repository: it contains {len(file_tree)} file(s) "
            f"({ext_desc}), but no Python or Node source files, test files, "
            "or dependency/build manifest were found anywhere in it."
        )

    @staticmethod
    def _merge_testing_state(
        previous: TestingState | None,
        result: TestingState | None,
        attempt_number: int,
    ) -> TestingState:

        if result is None:
            return previous or TestingState(passed=True, status=TestStatus.PASSED, attempt_number=attempt_number)

        if previous is None:
            return result

        combined_stdout = "\n\n".join(part for part in (previous.stdout, result.stdout) if part)
        combined_stderr = "\n\n".join(part for part in (previous.stderr, result.stderr) if part)
        combined_command = (previous.command or []) + (result.command or [])

        return TestingState(
            status=result.status if not result.passed else previous.status,
            command=combined_command or None,
            exit_code=result.exit_code if not result.passed else previous.exit_code,
            stdout=combined_stdout,
            stderr=combined_stderr,
            passed=previous.passed and result.passed,
            total_tests=previous.total_tests + result.total_tests,
            passed_tests=previous.passed_tests + result.passed_tests,
            skipped_tests=previous.skipped_tests + result.skipped_tests,
            failed_tests=previous.failed_tests + result.failed_tests,
            duration_seconds=(previous.duration_seconds or 0) + (result.duration_seconds or 0),
            timed_out=previous.timed_out or result.timed_out,
            attempt_number=attempt_number,
            framework=previous.framework or result.framework,
            working_directory=previous.working_directory or result.working_directory,
            testing_summary=(
                previous.testing_summary
                if previous.testing_summary and not result.passed and previous.status != TestStatus.PASSED
                else result.testing_summary
            ),
        )

    def debugger(
        self,
        state: WorkflowState,
    ) -> WorkflowState:
        state = self.debugger_agent.run(state)

        if state.execution.last_repair_trigger not in (
            RepairTrigger.STATIC_VALIDATION_FAILURE,
            RepairTrigger.REVIEW_FEEDBACK,
            RepairTrigger.REPOSITORY_COMPLETENESS_FAILURE,
            RepairTrigger.DEPENDENCY_RESOLUTION_FAILURE,
        ):
            state.execution.last_repair_trigger = RepairTrigger.TEST_FAILURE

        return state

    def reviewer(
        self,
        state: WorkflowState,
    ) -> WorkflowState:
        run_id = getattr(state.execution, "run_id", None) or (
            Path(state.project.output_directory).name if state.project.output_directory else "unknown"
        )

        upcoming_attempt = state.execution.review_retry_count + 1

        if self.event_dispatcher:
            self.event_dispatcher.emit(WorkflowEvent(
                event_type=EventType.REVIEWER_ATTEMPT_STARTED,
                run_id=run_id,
                agent=AgentType.REVIEWER,
                metadata={"attempt": upcoming_attempt},
            ))

        state = self.reviewer_agent.run(state)

        if self.event_dispatcher:
            self.event_dispatcher.emit(WorkflowEvent(
                event_type=EventType.REVIEWER_ATTEMPT_COMPLETED,
                run_id=run_id,
                agent=AgentType.REVIEWER,
                metadata={
                    "attempt": state.review.attempt_number,
                    "passed": state.review.passed,
                    "score": state.review.score,
                    "issue_count": len(state.review.issues),
                },
            ))

        if state.review.passed:
            logger.info("Review passed (score=%.1f)", state.review.score)
            return state

        state.execution.last_repair_trigger = RepairTrigger.REVIEW_FEEDBACK
        state.execution.review_retry_count += 1

        has_critical_finding = any(
            issue.severity == Severity.CRITICAL for issue in state.review.issues
        )

        if state.execution.review_retry_count >= MAX_REVIEW_ATTEMPTS and not has_critical_finding:
            highest_severity = min(
                (issue.severity for issue in state.review.issues),
                key=list(Severity).index,
                default=None,
            )

            state.review.auto_passed = True
            state.review.auto_pass_reason = "review_attempt_limit_reached"

            if self.event_dispatcher:
                self.event_dispatcher.emit(WorkflowEvent(
                    event_type=EventType.REVIEWER_AUTO_PASSED,
                    run_id=run_id,
                    agent=AgentType.REVIEWER,
                    metadata={
                        "attempts": state.review.attempt_number,
                        "original_verdict": "failed",
                        "issue_count": len(state.review.issues),
                        "highest_severity": highest_severity.value if highest_severity else None,
                        "reason": state.review.auto_pass_reason,
                    },
                ))

            logger.warning(
                "Review failed twice (score=%.1f, %d issue(s), no critical finding); "
                "auto-passing with warnings -- proceeding to documentation",
                state.review.score,
                len(state.review.issues),
            )

            return state

        if state.execution.review_retry_count > MAX_REVIEW_RETRIES:
            state.execution.workflow_status = WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES
            state.execution.current_step = (
                "Review retry limit exceeded"
            )
            state.execution.error_message = (
                "Implementation failed review after the maximum "
                f"number of retries ({MAX_REVIEW_RETRIES})."
            )
            logger.error(
                "Review retry limit reached after %d attempts; "
                "verification incomplete, repository preserved",
                MAX_REVIEW_RETRIES,
            )
        else:
            if self.event_dispatcher:
                self.event_dispatcher.emit(WorkflowEvent(
                    event_type=EventType.REVIEWER_REPAIR_REQUESTED,
                    run_id=run_id,
                    agent=AgentType.REVIEWER,
                    metadata={
                        "attempt": state.review.attempt_number,
                        "has_critical_finding": has_critical_finding,
                    },
                ))

            logger.warning(
                "Review failed (score=%.1f); retrying developer (%d/%d)",
                state.review.score,
                state.execution.review_retry_count,
                MAX_REVIEW_RETRIES,
            )

        return state

    def documentation(
        self,
        state: WorkflowState,
    ) -> WorkflowState:
        previous_written_files = list(
            state.documentation.written_files
        )

        state = self.documentation_agent.run(state)

        state.documentation = self.materialization_service.materialize_documentation(
            project=state.project,
            documentation=state.documentation,
            previous_written_files=previous_written_files,
        )

        logger.info("Workflow completed")

        return state
