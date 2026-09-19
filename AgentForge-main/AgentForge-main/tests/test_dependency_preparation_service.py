
from __future__ import annotations

from pathlib import Path

from backend.services.dependency_preparation_service import DependencyPreparationService
from backend.services.pip_failure_classifier import PipFailureKind
from backend.services.project_venv import venv_python_path
from backend.state.test_plan import TestPlan, TestStage
from backend.tools.base_tool import ToolResult
from backend.tools.terminal_tool import TerminalTool
from backend.tools.tool_registry import ToolRegistry


def _plan(**overrides) -> TestPlan:
    defaults = dict(
        framework="pytest",
        runtime="python",
        working_directory=".",
        stages=[TestStage(name="full_suite", command=["python", "-m", "pytest"])],
        targeted_test_capability=True,
        test_files=["test_x.py"],
        configuration_files=[],
        dependency_manifest="requirements.txt",
        package_manager="pip",
    )
    defaults.update(overrides)
    return TestPlan(**defaults)


def _service(workspace: Path) -> DependencyPreparationService:
    registry = ToolRegistry()
    registry.register(TerminalTool(workspace=workspace))
    return DependencyPreparationService(registry)


def test_skips_when_plan_has_no_manifest(tmp_path: Path) -> None:
    service = _service(tmp_path)
    plan = _plan(dependency_manifest=None, package_manager=None)

    result = service.prepare(project_root=str(tmp_path), plan=plan)

    assert result.skipped is True
    assert result.success is True


def test_installs_from_real_requirements_txt(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("requests\n", encoding="utf-8")
    service = _service(tmp_path)
    plan = _plan(dependency_manifest="requirements.txt", package_manager="pip")

    result = service.prepare(project_root=str(tmp_path), plan=plan)

    assert result.skipped is False
    assert result.command[1:] == ["-m", "pip", "install", "-r", "requirements.txt"]
    assert result.command[0] == str(venv_python_path(tmp_path))
    assert (tmp_path / ".venv").exists()
    assert result.success is True


def test_installs_into_isolated_venv_not_agentforges_own_environment(tmp_path: Path) -> None:

    (tmp_path / "requirements.txt").write_text("requests\n", encoding="utf-8")
    service = _service(tmp_path)
    plan = _plan(dependency_manifest="requirements.txt", package_manager="pip")

    result = service.prepare(project_root=str(tmp_path), plan=plan)

    assert result.success is True
    venv_site_packages = list((tmp_path / ".venv").rglob("requests"))
    assert venv_site_packages, "requests was not installed into the project's own venv"


def test_failure_reports_real_stderr_not_a_fabricated_message(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text(
        "this-package-definitely-does-not-exist-ever-12345\n", encoding="utf-8"
    )
    service = _service(tmp_path)
    plan = _plan(dependency_manifest="requirements.txt", package_manager="pip")

    result = service.prepare(project_root=str(tmp_path), plan=plan)

    assert result.success is False
    assert result.error_message is not None
    assert "exited with code" in result.error_message


def test_npm_install_command_shape(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"name": "x"}', encoding="utf-8")
    service = _service(tmp_path)
    plan = _plan(
        framework="jest",
        runtime="node",
        dependency_manifest="package.json",
        package_manager="npm",
    )

    command = DependencyPreparationService._build_command(plan)
    assert command == ["npm", "install"]


def test_working_directory_is_respected_for_sub_project(tmp_path: Path) -> None:
    sub = tmp_path / "backend"
    sub.mkdir()
    (sub / "requirements.txt").write_text("requests\n", encoding="utf-8")

    service = _service(tmp_path)
    plan = _plan(working_directory="backend", dependency_manifest="backend/requirements.txt")

    result = service.prepare(project_root=str(tmp_path), plan=plan)

    assert result.working_directory == "backend"
    assert result.command[1:] == ["-m", "pip", "install", "-r", "requirements.txt"]
    assert result.command[0] == str(venv_python_path(sub))


class _ScriptedTerminalTool:

    def __init__(self, results: list[ToolResult]) -> None:
        self._results = results
        self.calls = 0

    def get(self, name: str):
        assert name == "terminal"
        return self

    def run(self, *, command, cwd, timeout):
        result = self._results[min(self.calls, len(self._results) - 1)]
        self.calls += 1
        return result


def _transient_failure_result() -> ToolResult:
    return ToolResult(
        success=False,
        output={"stdout": "", "stderr": "ReadTimeoutError: Read timed out.", "return_code": 1},
    )


def _success_result() -> ToolResult:
    return ToolResult(success=True, output={"stdout": "Successfully installed x\n", "stderr": "", "return_code": 0})


def test_transient_failure_is_retried_and_succeeds(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "requirements.txt").write_text("x\n", encoding="utf-8")
    (tmp_path / ".venv" / "Scripts").mkdir(parents=True)
    (tmp_path / ".venv" / "Scripts" / "python.exe").touch()
    monkeypatch.setattr(
        "backend.services.dependency_preparation_service.ensure_pytest_installed",
        lambda python_path: None,
    )

    terminal = _ScriptedTerminalTool([_transient_failure_result(), _success_result()])
    registry = type("R", (), {"get": staticmethod(lambda name: terminal)})()
    service = DependencyPreparationService(registry, max_retries=2, retry_delay_seconds=0)
    plan = _plan()

    result = service.prepare(project_root=str(tmp_path), plan=plan)

    assert result.success is True
    assert terminal.calls == 2
    assert result.attempts == 2


def test_transient_failure_exhausts_retries_and_gives_up(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "requirements.txt").write_text("x\n", encoding="utf-8")
    (tmp_path / ".venv" / "Scripts").mkdir(parents=True)
    (tmp_path / ".venv" / "Scripts" / "python.exe").touch()
    monkeypatch.setattr(
        "backend.services.dependency_preparation_service.ensure_pytest_installed",
        lambda python_path: None,
    )

    terminal = _ScriptedTerminalTool([_transient_failure_result()])
    registry = type("R", (), {"get": staticmethod(lambda name: terminal)})()
    service = DependencyPreparationService(registry, max_retries=2, retry_delay_seconds=0)
    plan = _plan()

    result = service.prepare(project_root=str(tmp_path), plan=plan)

    assert result.success is False
    assert result.failure_kind == PipFailureKind.TRANSIENT
    assert terminal.calls == 3
    assert result.attempts == 3


def test_genuine_dependency_error_is_never_retried(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "requirements.txt").write_text("badpkg==99.99.99\n", encoding="utf-8")
    (tmp_path / ".venv" / "Scripts").mkdir(parents=True)
    (tmp_path / ".venv" / "Scripts" / "python.exe").touch()
    monkeypatch.setattr(
        "backend.services.dependency_preparation_service.ensure_pytest_installed",
        lambda python_path: None,
    )

    dependency_error_result = ToolResult(
        success=False,
        output={
            "stdout": "",
            "stderr": "ERROR: No matching distribution found for badpkg==99.99.99\n",
            "return_code": 1,
        },
    )
    terminal = _ScriptedTerminalTool([dependency_error_result, _success_result()])
    registry = type("R", (), {"get": staticmethod(lambda name: terminal)})()
    service = DependencyPreparationService(registry, max_retries=2, retry_delay_seconds=0)
    plan = _plan()

    result = service.prepare(project_root=str(tmp_path), plan=plan)

    assert result.success is False
    assert result.failure_kind == PipFailureKind.DEPENDENCY_ERROR
    assert terminal.calls == 1
    assert result.attempts == 1
