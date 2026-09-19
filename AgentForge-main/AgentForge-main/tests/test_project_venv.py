from __future__ import annotations

import sys
from pathlib import Path

import pytest

from backend.services.project_venv import (
    ensure_pytest_installed,
    ensure_venv,
    substitute_python_executable,
    venv_python_path,
)


def test_venv_python_path_matches_platform_layout(tmp_path: Path) -> None:
    path = venv_python_path(tmp_path)

    assert path.parent.parent == tmp_path / ".venv"
    if sys.platform == "win32":
        assert path.name == "python.exe"
        assert path.parent.name == "Scripts"
    else:
        assert path.name == "python"
        assert path.parent.name == "bin"


def test_substitute_replaces_leading_python_token(tmp_path: Path) -> None:
    fake_python = tmp_path / "fake_python.exe"

    result = substitute_python_executable(["python", "-m", "pytest"], fake_python)

    assert result == [str(fake_python), "-m", "pytest"]


def test_substitute_replaces_python3_token_too(tmp_path: Path) -> None:
    fake_python = tmp_path / "fake_python.exe"

    result = substitute_python_executable(["python3", "-m", "pytest"], fake_python)

    assert result[0] == str(fake_python)


def test_substitute_leaves_non_python_commands_untouched(tmp_path: Path) -> None:
    fake_python = tmp_path / "fake_python.exe"

    result = substitute_python_executable(["npm", "test"], fake_python)

    assert result == ["npm", "test"]


def test_substitute_leaves_empty_command_untouched(tmp_path: Path) -> None:
    fake_python = tmp_path / "fake_python.exe"

    assert substitute_python_executable([], fake_python) == []


def test_ensure_venv_creates_a_real_isolated_environment(tmp_path: Path) -> None:
    python_path = ensure_venv(tmp_path)

    assert python_path.exists()
    assert python_path != Path(sys.executable)
    assert str(tmp_path) in str(python_path)


def test_ensure_venv_is_idempotent(tmp_path: Path) -> None:
    first = ensure_venv(tmp_path)
    first_mtime = first.stat().st_mtime

    second = ensure_venv(tmp_path)

    assert second == first
    assert second.stat().st_mtime == first_mtime


def test_ensure_venv_raises_clearly_when_creation_fails(tmp_path: Path, monkeypatch) -> None:
    import subprocess

    def _fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args, returncode=1, stdout="", stderr="disk full")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    with pytest.raises(RuntimeError, match="disk full"):
        ensure_venv(tmp_path)


def test_ensure_pytest_installed_provisions_a_missing_pytest(tmp_path: Path) -> None:

    python_path = ensure_venv(tmp_path)

    check_before = __import__("subprocess").run(
        [str(python_path), "-c", "import pytest"], capture_output=True
    )
    assert check_before.returncode != 0, "expected a fresh venv to not already have pytest"

    ensure_pytest_installed(python_path)

    check_after = __import__("subprocess").run(
        [str(python_path), "-c", "import pytest"], capture_output=True
    )
    assert check_after.returncode == 0


def test_ensure_pytest_installed_is_idempotent(tmp_path: Path) -> None:
    python_path = ensure_venv(tmp_path)

    ensure_pytest_installed(python_path)
    ensure_pytest_installed(python_path)


def test_ensure_pytest_installed_raises_clearly_on_failure(tmp_path: Path, monkeypatch) -> None:
    import subprocess

    def _fake_run(command, **kwargs):
        if "import pytest" in command:
            return subprocess.CompletedProcess(args=command, returncode=1, stdout="", stderr="")
        return subprocess.CompletedProcess(args=command, returncode=1, stdout="", stderr="network unreachable")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    with pytest.raises(RuntimeError, match="network unreachable"):
        ensure_pytest_installed(tmp_path / "fake_python.exe")
