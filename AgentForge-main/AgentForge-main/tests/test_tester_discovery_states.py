
from __future__ import annotations

from pathlib import Path

from backend.core.constants import MAX_TEST_RETRIES
from backend.graph.nodes import WorkflowNodes
from backend.graph.router import WorkflowRouter
from backend.services.environment_preflight_service import EnvironmentPreflightService, PreflightResult
from backend.services.repository_completeness_service import RepositoryCompletenessService
from backend.services.test_discovery_service import TestDiscoveryService
from backend.services.testing_service import TestingService
from backend.state.architecture_state import ArchitectureState
from backend.state.execution_state import FailureCategory, RepairTrigger, WorkflowStatus
from backend.state.project_state import ProjectState
from backend.state.repository_snapshot import RepositorySnapshot
from backend.state.test_plan import TestPlan, TestStage
from backend.state.testing_state import DiscoveryStatus, TestingState, TestStatus
from backend.state.workflow_state import WorkflowState
from backend.tools.filesystem_tool import FilesystemTool
from backend.tools.terminal_tool import TerminalTool
from backend.tools.tool_registry import ToolRegistry
from langgraph.graph import END

from tests.support.workflow_node_fixtures import StubRepositoryIntegrityValidator


class _RecordingTesterAgent:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, state: WorkflowState) -> WorkflowState:
        self.calls += 1
        return state


class _RecordingDebuggerAgent:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, state: WorkflowState) -> WorkflowState:
        self.calls += 1
        return state


def _always_pass_preflight():
    return type("P", (), {"check": staticmethod(lambda **kw: PreflightResult(passed=True, issues=[]))})()


def _stub_nodes(**kwargs) -> WorkflowNodes:
    defaults = dict(
        analysis_agent=None,
        planner_agent=None,
        architect_agent=None,
        developer_agent=None,
        debugger_agent=_RecordingDebuggerAgent(),
        reviewer_agent=None,
        documentation_agent=None,
        materialization_service=None,
        tester_agent=_RecordingTesterAgent(),
        testing_service=None,
        repository_integrity_validator=StubRepositoryIntegrityValidator(),
        environment_preflight_service=_always_pass_preflight(),
        dependency_preparation_service=None,
        repository_completeness_service=RepositoryCompletenessService(),
    )
    defaults.update(kwargs)
    return WorkflowNodes(**defaults)


def _state(*, backend: str | None = None, frontend: str | None = None, summary: str | None = None) -> WorkflowState:
    state = WorkflowState()
    state.project = ProjectState(output_directory="workspace/proj_stub", backend=backend, frontend=frontend)
    state.architecture = ArchitectureState(architecture_summary=summary)
    return state




class _EmptySnapshotIntegrityValidator:
    def create_snapshot(self, output_directory, state=None) -> RepositorySnapshot:
        return RepositorySnapshot(project_root=output_directory or "stub", file_tree=[])

    def validate_repository(self, output_directory, *, state=None, written_files=None, raise_on_error=False):
        from backend.services.repository_integrity_validator import IntegrityCheckResult

        return IntegrityCheckResult(is_valid=False, issues=[])


def test_empty_repository_is_a_repairable_completeness_error_not_terminal() -> None:
    tester_agent = _RecordingTesterAgent()
    debugger = _RecordingDebuggerAgent()
    nodes = _stub_nodes(
        tester_agent=tester_agent,
        debugger_agent=debugger,
        repository_integrity_validator=_EmptySnapshotIntegrityValidator(),
    )
    state = _state(backend="FastAPI", summary="A FastAPI backend.")

    result = nodes.tester(state)

    assert result.testing.classification == FailureCategory.REPOSITORY_COMPLETENESS_ERROR
    assert result.testing.passed is False
    assert result.execution.workflow_status != WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES
    assert result.execution.last_repair_trigger == RepairTrigger.REPOSITORY_COMPLETENESS_FAILURE
    assert result.execution.test_retry_count == 1
    assert WorkflowRouter.tester_router(result) == "debugger"
    assert tester_agent.calls == 0


def test_completeness_failure_exhausts_after_max_test_retries() -> None:
    nodes = _stub_nodes(repository_integrity_validator=_EmptySnapshotIntegrityValidator())
    state = _state()
    state.execution.test_retry_count = MAX_TEST_RETRIES

    result = nodes.tester(state)

    assert result.testing.classification == FailureCategory.REPOSITORY_COMPLETENESS_ERROR
    assert result.execution.workflow_status == WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES
    assert WorkflowRouter.tester_router(result) == END


class _MissingManifestIntegrityValidator:
    def create_snapshot(self, output_directory, state=None) -> RepositorySnapshot:
        return RepositorySnapshot(
            project_root=output_directory or "stub",
            file_tree=["frontend/app/page.tsx", "frontend/app/layout.tsx"],
        )

    def validate_repository(self, output_directory, *, state=None, written_files=None, raise_on_error=False):
        from backend.services.repository_integrity_validator import IntegrityCheckResult

        return IntegrityCheckResult(is_valid=True, issues=[])


def test_missing_required_manifest_routes_to_repair_not_test_discovery_error() -> None:
    tester_agent = _RecordingTesterAgent()
    nodes = _stub_nodes(
        tester_agent=tester_agent,
        repository_integrity_validator=_MissingManifestIntegrityValidator(),
    )
    state = _state(frontend="Next.js", summary="A Next.js application.")

    result = nodes.tester(state)

    assert result.testing.classification == FailureCategory.REPOSITORY_COMPLETENESS_ERROR
    assert result.testing.classification != FailureCategory.TEST_DISCOVERY_ERROR
    assert "package.json" in result.testing.testing_summary
    assert WorkflowRouter.tester_router(result) == "debugger"
    assert tester_agent.calls == 0




class _DocsOnlyIntegrityValidator:
    def create_snapshot(self, output_directory, state=None) -> RepositorySnapshot:
        return RepositorySnapshot(
            project_root=output_directory or "stub",
            file_tree=["README.md", "docs/architecture.md"],
        )

    def validate_repository(self, output_directory, *, state=None, written_files=None, raise_on_error=False):
        from backend.services.repository_integrity_validator import IntegrityCheckResult

        return IntegrityCheckResult(is_valid=True, issues=[])


def test_documentation_only_repository_is_terminal_not_recognized() -> None:
    tester_agent = _RecordingTesterAgent()
    debugger = _RecordingDebuggerAgent()
    nodes = _stub_nodes(
        tester_agent=tester_agent,
        debugger_agent=debugger,
        repository_integrity_validator=_DocsOnlyIntegrityValidator(),
        test_discovery_service=TestDiscoveryService(),
    )
    state = _state()

    result = nodes.tester(state)

    assert result.testing.classification == FailureCategory.TEST_DISCOVERY_ERROR
    assert result.testing.discovery_status == DiscoveryStatus.NOT_RECOGNIZED
    assert result.execution.workflow_status == WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES
    assert WorkflowRouter.tester_router(result) == END
    assert debugger.calls == 0
    assert tester_agent.calls == 0
    assert "2 file(s)" in result.testing.testing_summary
    assert ".md" in result.testing.testing_summary




class _NoStagesDiscoveryService:

    def discover(self, snapshot):
        return [
            TestPlan(
                framework="none",
                runtime="node",
                working_directory=".",
                stages=[],
                test_files=[],
                dependency_manifest="package.json",
                package_manager="npm",
            )
        ]


def test_zero_stage_plan_is_recognized_no_tests_not_silently_passed_as_tested() -> None:
    tester_agent = _RecordingTesterAgent()
    nodes = _stub_nodes(
        tester_agent=tester_agent,
        test_discovery_service=_NoStagesDiscoveryService(),
    )
    state = _state()

    result = nodes.tester(state)

    assert result.testing.passed is True
    assert result.testing.discovery_status == DiscoveryStatus.RECOGNIZED_NO_TESTS
    assert result.testing.tests_executed is False
    assert result.testing.tests_discovered is False
    assert result.testing.verification_method == "none"
    assert tester_agent.calls == 0
    assert WorkflowRouter.tester_router(result) == "reviewer"


class _CompileCheckOnlyDiscoveryService:
    def discover(self, snapshot):
        return [
            TestPlan(
                framework="none",
                runtime="python",
                working_directory=".",
                stages=[TestStage(name="compile_check", command=["python", "-m", "compileall", "."])],
                test_files=[],
            )
        ]


def test_compile_check_only_plan_is_recognized_no_tests_when_it_passes() -> None:
    tester_agent = _RecordingTesterAgent()
    nodes = _stub_nodes(
        tester_agent=tester_agent,
        test_discovery_service=_CompileCheckOnlyDiscoveryService(),
        testing_service=type(
            "T",
            (),
            {
                "execute_stage": staticmethod(
                    lambda **kw: TestingState(status=TestStatus.PASSED, passed=True, attempt_number=1)
                )
            },
        )(),
    )
    state = _state()

    result = nodes.tester(state)

    assert result.testing.passed is True
    assert result.testing.discovery_status == DiscoveryStatus.RECOGNIZED_NO_TESTS
    assert result.testing.tests_executed is False
    assert result.testing.verification_method == "compile_check"
    assert tester_agent.calls == 0


class _RealTestSuiteDiscoveryService:
    def discover(self, snapshot):
        return [
            TestPlan(
                framework="pytest",
                runtime="python",
                working_directory=".",
                stages=[TestStage(name="full_suite", command=["python", "-m", "pytest"])],
                targeted_test_capability=True,
                test_files=["test_x.py"],
                dependency_manifest="requirements.txt",
                package_manager="pip",
            )
        ]


def test_real_test_suite_passing_is_recognized_testable() -> None:
    tester_agent = _RecordingTesterAgent()
    nodes = _stub_nodes(
        tester_agent=tester_agent,
        test_discovery_service=_RealTestSuiteDiscoveryService(),
        testing_service=type(
            "T",
            (),
            {
                "execute_stage": staticmethod(
                    lambda **kw: TestingState(
                        status=TestStatus.PASSED, passed=True, attempt_number=1, total_tests=3, passed_tests=3,
                    )
                )
            },
        )(),
    )
    state = _state()

    result = nodes.tester(state)

    assert result.testing.passed is True
    assert result.testing.discovery_status == DiscoveryStatus.RECOGNIZED_TESTABLE
    assert result.testing.tests_executed is True
    assert result.testing.tests_discovered is True
    assert result.testing.verification_method == "pytest"
    assert tester_agent.calls == 0


def test_real_test_suite_failing_is_recognized_testable_and_invokes_tester() -> None:

    from backend.state.testing_state import TestFailure

    tester_agent = _RecordingTesterAgent()
    nodes = _stub_nodes(
        tester_agent=tester_agent,
        test_discovery_service=_RealTestSuiteDiscoveryService(),
        testing_service=type(
            "T",
            (),
            {
                "execute_stage": staticmethod(
                    lambda **kw: TestingState(
                        status=TestStatus.FAILED,
                        passed=False,
                        attempt_number=1,
                        failed_tests=[TestFailure(name="test_x", message="assertion failed")],
                    )
                )
            },
        )(),
    )
    state = _state()

    result = nodes.tester(state)

    assert result.testing.passed is False
    assert result.testing.discovery_status == DiscoveryStatus.RECOGNIZED_TESTABLE
    assert result.testing.tests_executed is True
    assert tester_agent.calls == 1
    assert WorkflowRouter.tester_router(result) == "debugger"




def test_real_python_project_without_manifest_is_recognized_and_tested(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "calc.py").write_text(
        "def add(a, b):\n    return a + b\n", encoding="utf-8"
    )
    (project_dir / "test_calc.py").write_text(
        "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )

    tool_registry = ToolRegistry()
    tool_registry.register(FilesystemTool(workspace=project_dir))
    tool_registry.register(TerminalTool(workspace=project_dir))

    from backend.services.repository_integrity_validator import RepositoryIntegrityValidator

    nodes = _stub_nodes(
        repository_integrity_validator=RepositoryIntegrityValidator(),
        test_discovery_service=TestDiscoveryService(),
        testing_service=TestingService(tool_registry),
        environment_preflight_service=EnvironmentPreflightService(),
    )
    state = WorkflowState()
    state.project = ProjectState(output_directory=str(project_dir))
    state.implementation.written_files = ["calc.py", "test_calc.py"]

    result = nodes.tester(state)

    assert result.testing.classification is None
    assert result.testing.passed is True
    assert result.testing.discovery_status == DiscoveryStatus.RECOGNIZED_TESTABLE
    assert result.testing.tests_executed is True
    assert result.testing.tests_discovered is True
    assert result.testing.verification_method == "pytest"
    assert result.testing.total_tests == 1
