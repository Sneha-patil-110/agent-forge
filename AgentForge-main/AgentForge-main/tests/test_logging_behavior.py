from __future__ import annotations

import contextlib
import json
import logging

import pytest
from langchain_core.messages import AIMessage

import backend.core.logging as logging_config
from backend.agents.base_agent import BaseAgent
from backend.core.constants import MAX_REVIEW_RETRIES, MAX_TEST_RETRIES
from backend.graph.nodes import WorkflowNodes
from backend.services.materialization_service import MaterializationService
from backend.state.execution_state import WorkflowStatus
from backend.state.implementation_state import GeneratedCode, ImplementationState
from backend.state.project_state import ProjectState
from backend.state.review_state import ReviewIssue, ReviewState, Severity
from backend.state.testing_state import TestingState, TestStatus
from backend.state.workflow_state import WorkflowState
from backend.tools.filesystem_tool import FilesystemTool
from backend.tools.tool_registry import ToolRegistry
from tests.support.workflow_node_fixtures import (
    StubDependencyPreparationService,
    StubEnvironmentPreflightService,
    StubRepositoryIntegrityValidator,
    StubTestDiscoveryService,
    StubTestingService,
)


@contextlib.contextmanager
def _clean_root_handlers():

    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_level = root.level
    root.handlers.clear()
    try:
        yield root
    finally:
        for handler in root.handlers:
            handler.close()
        root.handlers.clear()
        root.handlers.extend(original_handlers)
        root.setLevel(original_level)


@pytest.fixture
def isolated_log_dir(tmp_path, monkeypatch):

    log_dir = tmp_path / "logs"
    monkeypatch.setattr(logging_config, "LOG_DIR", log_dir)
    monkeypatch.setattr(logging_config, "LOG_FILE", log_dir / "app.log")
    return log_dir


def test_setup_logging_adds_console_and_file_handlers(isolated_log_dir) -> None:
    with _clean_root_handlers() as root:
        logging_config.setup_logging()

        assert len(root.handlers) == 2


def test_setup_logging_creates_log_file(isolated_log_dir) -> None:
    with _clean_root_handlers():
        logging_config.setup_logging()
        logging.getLogger("test").info("hello from test")

    assert isolated_log_dir.exists()
    log_file = isolated_log_dir / "app.log"
    assert log_file.exists()
    assert "hello from test" in log_file.read_text(encoding="utf-8")


def test_setup_logging_is_idempotent(isolated_log_dir) -> None:
    with _clean_root_handlers() as root:
        logging_config.setup_logging()
        logging_config.setup_logging()
        logging_config.setup_logging()

        assert len(root.handlers) == 2


def test_application_init_twice_does_not_duplicate_handlers(isolated_log_dir) -> None:
    from backend.core.app import Application

    with _clean_root_handlers() as root:
        Application()
        assert len(root.handlers) == 2

        Application()
        assert len(root.handlers) == 2


class _StubLLMService:
    def __init__(self, content: str) -> None:
        self.content = content

    def invoke(self, *, model_role, prompt, context, response_schema=None, extra_messages=None, **_):
        return AIMessage(content=self.content)


class _StubPromptService:
    def load(self, prompt_file: str) -> str:
        return "system prompt"


class _EchoAgent(BaseAgent[str]):
    def __init__(self, llm_service, fail: bool = False) -> None:
        super().__init__(_StubPromptService(), llm_service)
        self._fail = fail

    @property
    def name(self) -> str:
        return "analysis"

    @property
    def prompt_file(self) -> str:
        return "analysis.md"

    @property
    def model_role(self) -> str:
        return "analysis"

    def build_context(self, state: WorkflowState) -> str:
        return "context"

    def validate(self, response: AIMessage) -> str:
        if self._fail:
            raise RuntimeError("boom")
        return response.content

    def update_state(self, state: WorkflowState, validated_output: str) -> WorkflowState:
        return state


def test_agent_start_and_completion_logged_exactly_once(caplog) -> None:
    agent = _EchoAgent(_StubLLMService('{"ok": true}'))
    state = WorkflowState()

    with caplog.at_level(logging.INFO, logger="backend.agents.base_agent"):
        agent.run(state)

    started = [r for r in caplog.records if "started" in r.message]
    completed = [r for r in caplog.records if "completed" in r.message]

    assert len(started) == 1
    assert len(completed) == 1


def test_agent_failure_does_not_produce_duplicate_tracebacks(caplog) -> None:
    agent = _EchoAgent(_StubLLMService('{"ok": true}'), fail=True)
    state = WorkflowState()

    with caplog.at_level(logging.DEBUG, logger="backend.agents.base_agent"):
        with pytest.raises(Exception):
            agent.run(state)

    tracebacks = [r for r in caplog.records if r.exc_info is not None]

    assert len(tracebacks) == 1


class _StubReviewerAgent:
    def __init__(self, passed: bool, *, issues: list | None = None) -> None:
        self.passed = passed
        self.issues = issues or []

    def run(self, state: WorkflowState) -> WorkflowState:
        state.review = ReviewState(
            passed=self.passed,
            score=4.0,
            issues=self.issues,
            attempt_number=state.execution.review_retry_count + 1,
        )
        return state


class _StubTesterAgent:

    def run(self, state: WorkflowState) -> WorkflowState:
        return state


class _StubDebuggerAgent:
    def run(self, state: WorkflowState) -> WorkflowState:
        return state


def _make_nodes(
    reviewer_agent=None,
    *,
    testing_passed: bool | None = None,
) -> WorkflowNodes:
    return WorkflowNodes(
        analysis_agent=None,
        planner_agent=None,
        architect_agent=None,
        developer_agent=None,
        tester_agent=_StubTesterAgent(),
        debugger_agent=_StubDebuggerAgent(),
        reviewer_agent=reviewer_agent,
        documentation_agent=None,
        materialization_service=MaterializationService(tool_registry=None),
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


def test_workflow_started_logged_once_per_analysis_call(caplog) -> None:
    class _NoopAgent:
        def run(self, state):
            return state

    nodes = _make_nodes(reviewer_agent=None)
    nodes.analysis_agent = _NoopAgent()

    with caplog.at_level(logging.INFO, logger="backend.graph.nodes"):
        nodes.analysis(WorkflowState())

    started = [r for r in caplog.records if r.message == "Workflow started"]
    assert len(started) == 1


def test_workflow_completed_logged_once_on_documentation(caplog) -> None:
    class _NoopAgent:
        def run(self, state):
            return state

    nodes = _make_nodes(reviewer_agent=None)
    nodes.documentation_agent = _NoopAgent()

    with caplog.at_level(logging.INFO, logger="backend.graph.nodes"):
        nodes.documentation(WorkflowState())

    completed = [r for r in caplog.records if r.message == "Workflow completed"]
    assert len(completed) == 1


def test_review_retry_logged_once_as_warning(caplog) -> None:
    nodes = _make_nodes(reviewer_agent=_StubReviewerAgent(passed=False))

    with caplog.at_level(logging.WARNING, logger="backend.graph.nodes"):
        nodes.reviewer(WorkflowState())

    retry_warnings = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "retrying developer" in r.message
    ]
    assert len(retry_warnings) == 1


def test_retry_limit_exhaustion_logged_once_as_error(caplog) -> None:
    nodes = _make_nodes(
        reviewer_agent=_StubReviewerAgent(
            passed=False,
            issues=[ReviewIssue(title="t", description="d", severity=Severity.CRITICAL)],
        )
    )
    state = WorkflowState()
    state.execution.review_retry_count = MAX_REVIEW_RETRIES

    with caplog.at_level(logging.WARNING, logger="backend.graph.nodes"):
        result = nodes.reviewer(state)

    error_logs = [
        r for r in caplog.records
        if r.levelno == logging.ERROR and "retry limit reached" in r.message
    ]
    assert len(error_logs) == 1
    assert result.execution.workflow_status == WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES


def test_testing_failure_logged_once_as_warning(caplog) -> None:
    nodes = _make_nodes(testing_passed=False)

    with caplog.at_level(logging.WARNING, logger="backend.graph.nodes"):
        nodes.tester(WorkflowState())

    retry_warnings = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "routing to debugger" in r.message
    ]
    assert len(retry_warnings) == 1


def test_test_retry_limit_exhaustion_logged_once_as_error(caplog) -> None:
    nodes = _make_nodes(testing_passed=False)
    state = WorkflowState()
    state.execution.test_retry_count = MAX_TEST_RETRIES

    with caplog.at_level(logging.WARNING, logger="backend.graph.nodes"):
        result = nodes.tester(state)

    error_logs = [
        r for r in caplog.records
        if r.levelno == logging.ERROR and "retry limit reached" in r.message
    ]
    assert len(error_logs) == 1
    assert result.execution.workflow_status == WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES


def test_testing_success_logged_once_as_info(caplog) -> None:
    nodes = _make_nodes(testing_passed=True)

    with caplog.at_level(logging.INFO, logger="backend.graph.nodes"):
        nodes.tester(WorkflowState())

    passed_logs = [
        r for r in caplog.records
        if r.levelno == logging.INFO and "Testing passed" in r.message
    ]
    assert len(passed_logs) == 1


def test_materialization_summary_logged_once(caplog, tmp_path) -> None:
    output_directory = tmp_path / "project"
    output_directory.mkdir()

    tool_registry = ToolRegistry()
    tool_registry.register(FilesystemTool(workspace=output_directory))
    service = MaterializationService(tool_registry)

    project = ProjectState(output_directory=str(output_directory))
    implementation = ImplementationState(
        generated_code=[
            GeneratedCode(path="app.py", content="print(1)", language="python")
        ]
    )

    with caplog.at_level(
        logging.INFO, logger="backend.services.materialization_service"
    ):
        service.materialize(project=project, implementation=implementation)

    summaries = [r for r in caplog.records if "Materialized" in r.message]
    assert len(summaries) == 1


def test_materialization_partial_failure_logged_once_as_warning(caplog, tmp_path) -> None:
    output_directory = tmp_path / "project"
    output_directory.mkdir()

    tool_registry = ToolRegistry()
    tool_registry.register(FilesystemTool(workspace=output_directory))
    service = MaterializationService(tool_registry)

    project = ProjectState(output_directory=str(output_directory))
    implementation = ImplementationState(
        generated_code=[
            GeneratedCode(path="good.py", content="ok", language="python"),
            GeneratedCode(path="/etc/bad.py", content="x", language="python"),
        ]
    )

    with caplog.at_level(
        logging.WARNING, logger="backend.services.materialization_service"
    ):
        service.materialize(project=project, implementation=implementation)

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1


def test_logs_never_contain_secret_or_full_prompt_or_response(caplog) -> None:

    secret_marker = "gsk_super_secret_value_should_never_appear"
    prompt_text = "SYSTEM PROMPT WITH FULL INSTRUCTIONS " * 5
    response_payload = json.dumps(
        {
            "generated_code": [
                {
                    "path": "app.py",
                    "content": f"API_KEY = '{secret_marker}'\n" * 3,
                    "language": "python",
                    "description": "d",
                }
            ],
            "completed_tasks": [],
            "failed_tasks": [],
            "implementation_notes": None,
        }
    )

    class _PromptService:
        def load(self, prompt_file: str) -> str:
            return prompt_text

    class _LLM:
        def invoke(self, *, model_role, prompt, context, response_schema=None, extra_messages=None, **_):
            return AIMessage(content=response_payload)

    from backend.agents.developer_agent import DeveloperAgent

    agent = DeveloperAgent(_PromptService(), _LLM())
    state = WorkflowState()

    with caplog.at_level(logging.DEBUG):
        agent.run(state)

    full_log_text = "\n".join(r.message for r in caplog.records)

    assert secret_marker not in full_log_text
    assert prompt_text not in full_log_text
    assert response_payload not in full_log_text
    assert "API_KEY" not in full_log_text
