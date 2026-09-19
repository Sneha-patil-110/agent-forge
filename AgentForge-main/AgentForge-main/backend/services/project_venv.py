
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_VENV_DIR_NAME = ".venv"


def venv_dir(project_root: str | Path) -> Path:
    return Path(project_root) / _VENV_DIR_NAME


def venv_python_path(project_root: str | Path) -> Path:
    root = venv_dir(project_root)
    if sys.platform == "win32":
        return root / "Scripts" / "python.exe"
    return root / "bin" / "python"


def ensure_venv(project_root: str | Path, *, timeout: float = 120.0) -> Path:

    python_path = venv_python_path(project_root)

    if python_path.exists():
        return python_path

    result = subprocess.run(
        [sys.executable, "-m", "venv", str(venv_dir(project_root))],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )

    if result.returncode != 0 or not python_path.exists():
        raise RuntimeError(
            "Failed to create project virtual environment: "
            f"{(result.stderr or result.stdout).strip()}"
        )

    return python_path


def ensure_pytest_installed(python_path: str | Path, *, timeout: float = 60.0) -> None:

    python_path = str(python_path)

    check = subprocess.run(
        [python_path, "-c", "import pytest"],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if check.returncode == 0:
        return

    result = subprocess.run(
        [python_path, "-m", "pip", "install", "pytest"],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Failed to install pytest into the project virtual environment: "
            f"{(result.stderr or result.stdout).strip()}"
        )


def substitute_python_executable(command: list[str], python_path: Path) -> list[str]:

    if not command or command[0] not in ("python", "python3"):
        return command

    return [str(python_path), *command[1:]]
