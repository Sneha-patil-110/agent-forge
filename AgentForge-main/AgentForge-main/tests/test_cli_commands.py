from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pytest

from backend.cli import commands
from backend.core.exceptions import (
    InvalidRunIdError,
    RunCorruptedError,
    RunNotFoundError,
)
from backend.events.dispatcher import EventDispatcher
from backend.mcp.client_manager import MCPClientManager
from backend.mcp.config import MCPServerConfig, MCPTransport
from backend.mcp.registry import MCPToolRegistry
from backend.services.mcp_management_service import MCPManagementService
from backend.services.run_service import RunService
from backend.state.execution_state import WorkflowStatus
from backend.state.workflow_state import WorkflowState


class _FakeApplication:
    def __init__(
        self,
        *,
        start_result=None,
        start_exception=None,
        resume_result=None,
        resume_exception=None,
        run_service=None,
        mcp_management_service=None,
    ) -> None:
        self.event_dispatcher = EventDispatcher()
        self.run_service = run_service
        self._start_result = start_result
        self._start_exception = start_exception
        self._resume_result = resume_result
        self._resume_exception = resume_exception
        self.start_run_calls: list[str] = []
        self.resume_run_calls: list[str] = []
        self.mcp_management_service = mcp_management_service

    def start_run(self, request: str):
        self.start_run_calls.append(request)
        if self._start_exception is not None:
            raise self._start_exception
        return self._start_result

    def resume_run(self, run_id: str):
        self.resume_run_calls.append(run_id)
        if self._resume_exception is not None:
            raise self._resume_exception
        return self._resume_result


def _completed_state() -> WorkflowState:
    state = WorkflowState()
    state.execution.workflow_status = WorkflowStatus.COMPLETED
    return state


def _failed_state(message: str = "Testing failed after the maximum number of retries (3).") -> WorkflowState:
    state = WorkflowState()
    state.execution.workflow_status = WorkflowStatus.FAILED
    state.execution.error_message = message
    return state




def test_create_success_prints_run_id_and_exits_zero(monkeypatch, capsys) -> None:
    fake_app = _FakeApplication(start_result=("af_20260714_deadbeef", _completed_state()))
    monkeypatch.setattr(commands, "Application", lambda: fake_app)

    exit_code = commands.cmd_create(argparse.Namespace(request="Build a FastAPI expense tracker"))

    assert exit_code == commands.EXIT_SUCCESS
    assert fake_app.start_run_calls == ["Build a FastAPI expense tracker"]
    out = capsys.readouterr().out
    assert "af_20260714_deadbeef" in out
    assert "completed" in out


def test_create_subscribes_event_renderer(monkeypatch) -> None:
    fake_app = _FakeApplication(start_result=("af_20260714_deadbeef", _completed_state()))
    monkeypatch.setattr(commands, "Application", lambda: fake_app)

    commands.cmd_create(argparse.Namespace(request="anything"))

    assert len(fake_app.event_dispatcher._subscribers) == 1


def test_create_workflow_failure_exits_nonzero(monkeypatch, capsys) -> None:
    fake_app = _FakeApplication(start_result=("af_20260714_deadbeef", _failed_state()))
    monkeypatch.setattr(commands, "Application", lambda: fake_app)

    exit_code = commands.cmd_create(argparse.Namespace(request="anything"))

    assert exit_code == commands.EXIT_WORKFLOW_FAILED
    err = capsys.readouterr().err
    assert "maximum number of retries" in err


def test_create_unexpected_error_exits_nonzero(monkeypatch, capsys) -> None:
    fake_app = _FakeApplication(start_exception=RuntimeError("boom"))
    monkeypatch.setattr(commands, "Application", lambda: fake_app)

    exit_code = commands.cmd_create(argparse.Namespace(request="anything"))

    assert exit_code == commands.EXIT_UNEXPECTED_ERROR
    assert "boom" in capsys.readouterr().err




def test_resume_success_prints_status_and_exits_zero(monkeypatch, capsys) -> None:
    fake_app = _FakeApplication(resume_result=(_completed_state(), False))
    monkeypatch.setattr(commands, "Application", lambda: fake_app)

    exit_code = commands.cmd_resume(argparse.Namespace(run_id="af_20260714_deadbeef"))

    assert exit_code == commands.EXIT_SUCCESS
    assert fake_app.resume_run_calls == ["af_20260714_deadbeef"]
    assert "completed" in capsys.readouterr().out


def test_resume_invalid_run_id_exits_with_invalid_argument_code(monkeypatch, capsys) -> None:
    fake_app = _FakeApplication(resume_exception=InvalidRunIdError("bad run id"))
    monkeypatch.setattr(commands, "Application", lambda: fake_app)

    exit_code = commands.cmd_resume(argparse.Namespace(run_id="../../escape"))

    assert exit_code == commands.EXIT_INVALID_ARGUMENT
    assert "bad run id" in capsys.readouterr().err


def test_resume_missing_run_exits_with_not_found_code(monkeypatch, capsys) -> None:
    fake_app = _FakeApplication(resume_exception=RunNotFoundError("not found"))
    monkeypatch.setattr(commands, "Application", lambda: fake_app)

    exit_code = commands.cmd_resume(argparse.Namespace(run_id="af_20260714_deadbeef"))

    assert exit_code == commands.EXIT_RUN_NOT_FOUND


def test_resume_already_completed_run_does_not_reexecute(monkeypatch, capsys) -> None:
    fake_app = _FakeApplication(resume_result=(_completed_state(), True))
    monkeypatch.setattr(commands, "Application", lambda: fake_app)

    exit_code = commands.cmd_resume(argparse.Namespace(run_id="af_20260714_deadbeef"))

    assert exit_code == commands.EXIT_SUCCESS
    out = capsys.readouterr().out
    assert "already" in out
    assert "nothing to resume" in out


def test_resume_already_failed_run_reports_failure_exit_code(monkeypatch, capsys) -> None:
    fake_app = _FakeApplication(resume_result=(_failed_state(), True))
    monkeypatch.setattr(commands, "Application", lambda: fake_app)

    exit_code = commands.cmd_resume(argparse.Namespace(run_id="af_20260714_deadbeef"))

    assert exit_code == commands.EXIT_WORKFLOW_FAILED




@pytest.fixture
def run_service(tmp_path: Path) -> RunService:
    return RunService(runs_root=tmp_path / "runs")


@pytest.fixture
def fake_app_with_real_run_service(run_service: RunService) -> _FakeApplication:
    return _FakeApplication(run_service=run_service)


def test_status_valid_run(monkeypatch, capsys, run_service, fake_app_with_real_run_service) -> None:
    metadata = run_service.create_run()
    monkeypatch.setattr(commands, "Application", lambda: fake_app_with_real_run_service)

    exit_code = commands.cmd_status(argparse.Namespace(run_id=metadata.run_id))

    assert exit_code == commands.EXIT_SUCCESS
    out = capsys.readouterr().out
    assert metadata.run_id in out
    assert "Status:" in out
    assert "Created:" in out
    assert "Updated:" in out


def test_status_missing_run(monkeypatch, capsys, fake_app_with_real_run_service) -> None:
    monkeypatch.setattr(commands, "Application", lambda: fake_app_with_real_run_service)

    exit_code = commands.cmd_status(argparse.Namespace(run_id="af_20260714_deadbeef"))

    assert exit_code == commands.EXIT_RUN_NOT_FOUND


def test_status_invalid_run_id(monkeypatch, capsys, fake_app_with_real_run_service) -> None:
    monkeypatch.setattr(commands, "Application", lambda: fake_app_with_real_run_service)

    exit_code = commands.cmd_status(argparse.Namespace(run_id="../../escape"))

    assert exit_code == commands.EXIT_INVALID_ARGUMENT


def test_status_corrupted_metadata(monkeypatch, capsys, run_service, fake_app_with_real_run_service) -> None:
    metadata = run_service.create_run()
    (run_service.run_dir(metadata.run_id) / "metadata.json").write_text("not json", encoding="utf-8")
    monkeypatch.setattr(commands, "Application", lambda: fake_app_with_real_run_service)

    exit_code = commands.cmd_status(argparse.Namespace(run_id=metadata.run_id))

    assert exit_code == commands.EXIT_RUN_CORRUPTED


def test_runs_no_runs(monkeypatch, capsys, fake_app_with_real_run_service) -> None:
    monkeypatch.setattr(commands, "Application", lambda: fake_app_with_real_run_service)

    exit_code = commands.cmd_runs(argparse.Namespace())

    assert exit_code == commands.EXIT_SUCCESS
    assert "No runs found" in capsys.readouterr().out


def test_runs_single_run(monkeypatch, capsys, run_service, fake_app_with_real_run_service) -> None:
    metadata = run_service.create_run()
    monkeypatch.setattr(commands, "Application", lambda: fake_app_with_real_run_service)

    exit_code = commands.cmd_runs(argparse.Namespace())

    assert exit_code == commands.EXIT_SUCCESS
    assert metadata.run_id in capsys.readouterr().out


def test_runs_multiple_runs_ordered_most_recently_updated_first(
    monkeypatch, capsys, run_service, fake_app_with_real_run_service
) -> None:
    import time

    first = run_service.create_run()
    time.sleep(0.01)
    second = run_service.create_run()

    monkeypatch.setattr(commands, "Application", lambda: fake_app_with_real_run_service)

    exit_code = commands.cmd_runs(argparse.Namespace())

    assert exit_code == commands.EXIT_SUCCESS
    out = capsys.readouterr().out
    assert out.index(second.run_id) < out.index(first.run_id)


def test_runs_corrupted_metadata_shown_not_hidden(
    monkeypatch, capsys, run_service, fake_app_with_real_run_service
) -> None:
    metadata = run_service.create_run()
    (run_service.run_dir(metadata.run_id) / "metadata.json").write_text("not json", encoding="utf-8")
    monkeypatch.setattr(commands, "Application", lambda: fake_app_with_real_run_service)

    exit_code = commands.cmd_runs(argparse.Namespace())

    assert exit_code == commands.EXIT_SUCCESS
    out = capsys.readouterr().out
    assert metadata.run_id in out
    assert "corrupted" in out


def test_inspect_valid_run_shows_expected_fields(
    monkeypatch, capsys, run_service, fake_app_with_real_run_service
) -> None:
    metadata = run_service.create_run()
    state = run_service.load_state(metadata.run_id)
    state.project.project_name = "Expense Tracker"
    state.execution.test_retry_count = 1
    state.execution.review_retry_count = 2
    run_service.save_state(metadata.run_id, state)

    monkeypatch.setattr(commands, "Application", lambda: fake_app_with_real_run_service)

    exit_code = commands.cmd_inspect(argparse.Namespace(run_id=metadata.run_id))

    assert exit_code == commands.EXIT_SUCCESS
    out = capsys.readouterr().out
    assert "Expense Tracker" in out
    assert "Test retry count: 1" in out
    assert "Review retry count: 2" in out
    assert "Files materialized:" in out


def test_inspect_missing_run(monkeypatch, capsys, fake_app_with_real_run_service) -> None:
    monkeypatch.setattr(commands, "Application", lambda: fake_app_with_real_run_service)

    exit_code = commands.cmd_inspect(argparse.Namespace(run_id="af_20260714_deadbeef"))

    assert exit_code == commands.EXIT_RUN_NOT_FOUND




def test_docs_lists_generated_documents(
    monkeypatch, capsys, run_service, fake_app_with_real_run_service
) -> None:
    from backend.state.documentation_state import DocumentationFile

    metadata = run_service.create_run()
    state = run_service.load_state(metadata.run_id)
    state.documentation.generated_docs = [
        DocumentationFile(title="Overview", path="README.md", content="# Overview\n"),
        DocumentationFile(title="Deploy", path="docs/deployment.md", content="# Deploy\n"),
    ]
    state.documentation.written_files = ["README.md"]
    state.documentation.file_write_errors = ["docs/deployment.md: disk full"]
    run_service.save_state(metadata.run_id, state)

    monkeypatch.setattr(commands, "Application", lambda: fake_app_with_real_run_service)

    exit_code = commands.cmd_docs(argparse.Namespace(run_id=metadata.run_id, path=None, metadata=False, output=None))

    assert exit_code == commands.EXIT_SUCCESS
    out = capsys.readouterr().out
    assert "README.md" in out
    assert "docs/deployment.md" in out
    assert "generated" in out
    assert "failed" in out


def test_docs_no_documents_generated(monkeypatch, capsys, run_service, fake_app_with_real_run_service) -> None:
    metadata = run_service.create_run()
    monkeypatch.setattr(commands, "Application", lambda: fake_app_with_real_run_service)

    exit_code = commands.cmd_docs(argparse.Namespace(run_id=metadata.run_id, path=None, metadata=False, output=None))

    assert exit_code == commands.EXIT_SUCCESS
    assert "No documentation generated" in capsys.readouterr().out


def test_docs_missing_run_exits_not_found(monkeypatch, fake_app_with_real_run_service) -> None:
    monkeypatch.setattr(commands, "Application", lambda: fake_app_with_real_run_service)

    exit_code = commands.cmd_docs(
        argparse.Namespace(run_id="af_20260714_deadbeef", path=None, metadata=False, output=None)
    )

    assert exit_code == commands.EXIT_RUN_NOT_FOUND


def test_docs_prints_content_for_a_specific_path(
    monkeypatch, capsys, run_service, fake_app_with_real_run_service
) -> None:
    from backend.state.documentation_state import DocumentationFile

    metadata = run_service.create_run()
    state = run_service.load_state(metadata.run_id)
    state.documentation.generated_docs = [
        DocumentationFile(title="Overview", path="README.md", content="# Overview\n\nDetails.\n"),
    ]
    state.documentation.written_files = ["README.md"]
    run_service.save_state(metadata.run_id, state)

    monkeypatch.setattr(commands, "Application", lambda: fake_app_with_real_run_service)

    exit_code = commands.cmd_docs(
        argparse.Namespace(run_id=metadata.run_id, path="README.md", metadata=False, output=None)
    )

    assert exit_code == commands.EXIT_SUCCESS
    assert capsys.readouterr().out == "# Overview\n\nDetails.\n\n"


def test_docs_unknown_path_exits_invalid_argument(
    monkeypatch, capsys, run_service, fake_app_with_real_run_service
) -> None:
    metadata = run_service.create_run()
    monkeypatch.setattr(commands, "Application", lambda: fake_app_with_real_run_service)

    exit_code = commands.cmd_docs(
        argparse.Namespace(run_id=metadata.run_id, path="does-not-exist.md", metadata=False, output=None)
    )

    assert exit_code == commands.EXIT_INVALID_ARGUMENT
    assert "not found" in capsys.readouterr().err


def test_docs_metadata_flag_prints_metadata_not_content(
    monkeypatch, capsys, run_service, fake_app_with_real_run_service
) -> None:
    from backend.state.documentation_state import DocumentationFile

    metadata = run_service.create_run()
    state = run_service.load_state(metadata.run_id)
    state.documentation.generated_docs = [
        DocumentationFile(
            title="Overview", path="README.md", content="secret content", description="High-level summary."
        ),
    ]
    state.documentation.written_files = ["README.md"]
    run_service.save_state(metadata.run_id, state)

    monkeypatch.setattr(commands, "Application", lambda: fake_app_with_real_run_service)

    exit_code = commands.cmd_docs(
        argparse.Namespace(run_id=metadata.run_id, path="README.md", metadata=True, output=None)
    )

    assert exit_code == commands.EXIT_SUCCESS
    out = capsys.readouterr().out
    assert "Title: Overview" in out
    assert "High-level summary." in out
    assert "Generating agent: documentation" in out
    assert "Status: generated" in out
    assert "secret content" not in out


def test_docs_output_flag_writes_content_to_a_file(
    monkeypatch, capsys, tmp_path, run_service, fake_app_with_real_run_service
) -> None:
    from backend.state.documentation_state import DocumentationFile

    metadata = run_service.create_run()
    state = run_service.load_state(metadata.run_id)
    state.documentation.generated_docs = [
        DocumentationFile(title="Overview", path="README.md", content="# Overview\n"),
    ]
    state.documentation.written_files = ["README.md"]
    run_service.save_state(metadata.run_id, state)

    monkeypatch.setattr(commands, "Application", lambda: fake_app_with_real_run_service)

    destination = tmp_path / "exported.md"
    exit_code = commands.cmd_docs(
        argparse.Namespace(run_id=metadata.run_id, path="README.md", metadata=False, output=str(destination))
    )

    assert exit_code == commands.EXIT_SUCCESS
    assert destination.read_text(encoding="utf-8") == "# Overview\n"
    assert "Wrote README.md" in capsys.readouterr().out


def test_inspect_does_not_dump_generated_source_code(
    monkeypatch, capsys, run_service, fake_app_with_real_run_service
) -> None:
    from backend.state.implementation_state import GeneratedCode

    metadata = run_service.create_run()
    state = run_service.load_state(metadata.run_id)
    secret_marker = "def super_secret_implementation_detail(): pass"
    state.implementation.generated_code = [
        GeneratedCode(path="app.py", content=secret_marker, language="python")
    ]
    run_service.save_state(metadata.run_id, state)

    monkeypatch.setattr(commands, "Application", lambda: fake_app_with_real_run_service)

    exit_code = commands.cmd_inspect(argparse.Namespace(run_id=metadata.run_id))

    assert exit_code == commands.EXIT_SUCCESS
    out = capsys.readouterr().out
    assert secret_marker not in out




_MCP_TEST_SERVER_ARGS = ["-m", "tests.support.mcp_test_server"]


def _real_mcp_service(**overrides) -> MCPManagementService:
    defaults = dict(
        name="test",
        display_name="Test Server",
        enabled=True,
        transport=MCPTransport.STDIO,
        command=sys.executable,
        args=_MCP_TEST_SERVER_ARGS,
    )
    defaults.update(overrides)
    config = MCPServerConfig(**defaults)

    return MCPManagementService(
        client_manager=MCPClientManager({"test": config}),
        tool_registry=MCPToolRegistry(),
    )


def test_mcp_list_no_servers(monkeypatch, capsys) -> None:
    fake_app = _FakeApplication(mcp_management_service=MCPManagementService(
        client_manager=MCPClientManager({}), tool_registry=MCPToolRegistry()
    ))
    monkeypatch.setattr(commands, "Application", lambda: fake_app)

    exit_code = commands.cmd_mcp_list(argparse.Namespace())

    assert exit_code == commands.EXIT_SUCCESS
    assert "No MCP servers configured" in capsys.readouterr().out


def test_mcp_list_shows_configured_servers(monkeypatch, capsys) -> None:
    fake_app = _FakeApplication(mcp_management_service=_real_mcp_service())
    monkeypatch.setattr(commands, "Application", lambda: fake_app)

    exit_code = commands.cmd_mcp_list(argparse.Namespace())

    assert exit_code == commands.EXIT_SUCCESS
    assert "test" in capsys.readouterr().out


def test_mcp_inspect_unknown_server(monkeypatch, capsys) -> None:
    fake_app = _FakeApplication(mcp_management_service=_real_mcp_service())
    monkeypatch.setattr(commands, "Application", lambda: fake_app)

    exit_code = commands.cmd_mcp_inspect(argparse.Namespace(server_name="nope"))

    assert exit_code == commands.EXIT_INVALID_ARGUMENT
    assert "nope" in capsys.readouterr().err


def test_mcp_inspect_known_server(monkeypatch, capsys) -> None:
    fake_app = _FakeApplication(mcp_management_service=_real_mcp_service())
    monkeypatch.setattr(commands, "Application", lambda: fake_app)

    exit_code = commands.cmd_mcp_inspect(argparse.Namespace(server_name="test"))

    assert exit_code == commands.EXIT_SUCCESS
    out = capsys.readouterr().out
    assert "ID: test" in out
    assert "Display name: Test Server" in out


def test_mcp_test_connectivity_reports_online(monkeypatch, capfd) -> None:
    fake_app = _FakeApplication(mcp_management_service=_real_mcp_service())
    monkeypatch.setattr(commands, "Application", lambda: fake_app)

    exit_code = commands.cmd_mcp_test(argparse.Namespace(server_name="test"))

    assert exit_code == commands.EXIT_SUCCESS
    assert "Status: online" in capfd.readouterr().out


def test_mcp_test_unknown_server(monkeypatch, capsys) -> None:
    fake_app = _FakeApplication(mcp_management_service=_real_mcp_service())
    monkeypatch.setattr(commands, "Application", lambda: fake_app)

    exit_code = commands.cmd_mcp_test(argparse.Namespace(server_name="nope"))

    assert exit_code == commands.EXIT_INVALID_ARGUMENT


def test_mcp_health_all_enabled_servers(monkeypatch, capsys) -> None:
    fake_app = _FakeApplication(mcp_management_service=_real_mcp_service())
    monkeypatch.setattr(commands, "Application", lambda: fake_app)

    exit_code = commands.cmd_mcp_health(argparse.Namespace(server_name=None))

    assert exit_code == commands.EXIT_SUCCESS
    assert "test" in capsys.readouterr().out


def test_mcp_refresh_reports_refreshed_servers(monkeypatch, capfd) -> None:
    fake_app = _FakeApplication(mcp_management_service=_real_mcp_service())
    monkeypatch.setattr(commands, "Application", lambda: fake_app)

    exit_code = commands.cmd_mcp_refresh(argparse.Namespace())

    assert exit_code == commands.EXIT_SUCCESS
    assert "test" in capfd.readouterr().out


def test_mcp_tools_lists_discovered_tools_after_refresh(monkeypatch, capfd) -> None:
    fake_app = _FakeApplication(mcp_management_service=_real_mcp_service())
    monkeypatch.setattr(commands, "Application", lambda: fake_app)

    commands.cmd_mcp_refresh(argparse.Namespace())
    capfd.readouterr()

    exit_code = commands.cmd_mcp_tools(argparse.Namespace(server_name=None, query=None))

    assert exit_code == commands.EXIT_SUCCESS
    out = capfd.readouterr().out
    assert "test.echo" in out
