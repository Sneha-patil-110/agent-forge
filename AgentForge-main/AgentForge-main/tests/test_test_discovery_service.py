
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.services.test_discovery_service import TestDiscoveryService
from backend.state.repository_snapshot import RepositorySnapshot


@pytest.fixture
def discovery() -> TestDiscoveryService:
    return TestDiscoveryService()


def _snapshot(root: Path, file_tree: list[str]) -> RepositorySnapshot:
    return RepositorySnapshot(project_root=str(root), file_tree=sorted(file_tree))


def _write(root: Path, rel_path: str, content: str = "") -> None:
    full = root / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")


def test_python_project_with_requirements_and_pytest(tmp_path: Path) -> None:
    _write(tmp_path, "requirements.txt", "pytest\nfastapi\n")
    _write(tmp_path, "main.py", "x = 1\n")
    _write(tmp_path, "test_main.py", "def test_x(): assert True\n")

    snapshot = _snapshot(tmp_path, ["requirements.txt", "main.py", "test_main.py"])
    plans = discovery_service().discover(snapshot)

    assert len(plans) == 1
    plan = plans[0]
    assert plan.framework == "pytest"
    assert plan.runtime == "python"
    assert plan.working_directory == "."
    assert plan.dependency_manifest == "requirements.txt"
    assert plan.package_manager == "pip"
    assert plan.targeted_test_capability is True
    assert plan.stages[0].command == ["python", "-m", "pytest"]
    assert "test_main.py" in plan.test_files


def test_python_project_without_any_manifest_still_detected(tmp_path: Path) -> None:

    _write(tmp_path, "calc.py", "def add(a, b): return a + b\n")
    _write(tmp_path, "test_calc.py", "def test_add(): assert True\n")

    snapshot = _snapshot(tmp_path, ["calc.py", "test_calc.py"])
    plans = discovery_service().discover(snapshot)

    assert len(plans) == 1
    plan = plans[0]
    assert plan.framework == "pytest"
    assert plan.dependency_manifest is None
    assert plan.package_manager is None


def test_project_with_no_test_files_gets_compile_check_only(tmp_path: Path) -> None:
    _write(tmp_path, "requirements.txt", "fastapi\n")
    _write(tmp_path, "main.py", "x = 1\n")

    snapshot = _snapshot(tmp_path, ["requirements.txt", "main.py"])
    plans = discovery_service().discover(snapshot)

    assert len(plans) == 1
    plan = plans[0]
    assert plan.framework == "none"
    assert plan.test_files == []
    assert plan.stages[0].name == "compile_check"
    assert plan.stages[0].command == ["python", "-m", "compileall", "."]
    assert plan.targeted_test_capability is False


def test_node_project_with_configured_test_script(tmp_path: Path) -> None:
    package_json = {
        "name": "frontend",
        "scripts": {"test": "jest --coverage"},
        "devDependencies": {"jest": "^29.0.0"},
    }
    _write(tmp_path, "package.json", json.dumps(package_json))
    _write(tmp_path, "src/App.test.tsx", "test('x', () => {})\n")

    snapshot = _snapshot(tmp_path, ["package.json", "src/App.test.tsx"])
    plans = discovery_service().discover(snapshot)

    assert len(plans) == 1
    plan = plans[0]
    assert plan.framework == "npm-script"
    assert plan.runtime == "node"
    assert plan.stages[0].command == ["npm", "test"]
    assert plan.dependency_manifest == "package.json"
    assert plan.package_manager == "npm"


def test_node_project_with_vitest_dependency_and_no_test_script(tmp_path: Path) -> None:
    package_json = {
        "name": "frontend",
        "scripts": {"build": "vite build"},
        "devDependencies": {"vitest": "^1.0.0"},
    }
    _write(tmp_path, "package.json", json.dumps(package_json))
    _write(tmp_path, "src/App.test.ts", "test('x', () => {})\n")

    snapshot = _snapshot(tmp_path, ["package.json", "src/App.test.ts"])
    plans = discovery_service().discover(snapshot)

    assert len(plans) == 1
    plan = plans[0]
    assert plan.framework == "vitest"
    assert plan.stages[0].command == ["npx", "vitest", "run"]
    assert plan.targeted_test_capability is True


def test_node_project_with_no_scripts_and_no_framework_falls_back_to_build_check(tmp_path: Path) -> None:
    package_json = {"name": "frontend", "scripts": {"build": "next build"}}
    _write(tmp_path, "package.json", json.dumps(package_json))

    snapshot = _snapshot(tmp_path, ["package.json"])
    plans = discovery_service().discover(snapshot)

    assert len(plans) == 1
    plan = plans[0]
    assert plan.framework == "none"
    assert plan.stages[0].name == "build_check"
    assert plan.stages[0].command == ["npm", "run", "build"]


def test_backend_only_project_produces_one_plan(tmp_path: Path) -> None:
    _write(tmp_path, "backend/requirements.txt", "fastapi\npytest\n")
    _write(tmp_path, "backend/main.py", "x = 1\n")
    _write(tmp_path, "backend/test_main.py", "def test_x(): assert True\n")

    snapshot = _snapshot(
        tmp_path, ["backend/requirements.txt", "backend/main.py", "backend/test_main.py"]
    )
    plans = discovery_service().discover(snapshot)

    assert len(plans) == 1
    assert plans[0].runtime == "python"
    assert plans[0].working_directory == "backend"


def test_frontend_only_project_produces_one_plan(tmp_path: Path) -> None:
    package_json = {"name": "frontend", "scripts": {"test": "jest"}}
    _write(tmp_path, "frontend/package.json", json.dumps(package_json))
    _write(tmp_path, "frontend/src/App.test.tsx", "test('x', () => {})\n")

    snapshot = _snapshot(
        tmp_path, ["frontend/package.json", "frontend/src/App.test.tsx"]
    )
    plans = discovery_service().discover(snapshot)

    assert len(plans) == 1
    assert plans[0].runtime == "node"
    assert plans[0].working_directory == "frontend"


def test_backend_and_frontend_split_produces_two_independent_plans(tmp_path: Path) -> None:
    _write(tmp_path, "backend/requirements.txt", "fastapi\npytest\n")
    _write(tmp_path, "backend/main.py", "x = 1\n")
    _write(tmp_path, "backend/test_main.py", "def test_x(): assert True\n")

    package_json = {"name": "frontend", "scripts": {"test": "jest"}}
    _write(tmp_path, "frontend/package.json", json.dumps(package_json))
    _write(tmp_path, "frontend/src/App.test.tsx", "test('x', () => {})\n")

    snapshot = _snapshot(
        tmp_path,
        [
            "backend/requirements.txt",
            "backend/main.py",
            "backend/test_main.py",
            "frontend/package.json",
            "frontend/src/App.test.tsx",
        ],
    )
    plans = discovery_service().discover(snapshot)

    assert len(plans) == 2
    runtimes = {plan.runtime for plan in plans}
    assert runtimes == {"python", "node"}


def test_project_with_no_recognizable_language_produces_no_plans(tmp_path: Path) -> None:
    _write(tmp_path, "README.md", "# Just docs\n")

    snapshot = _snapshot(tmp_path, ["README.md"])
    plans = discovery_service().discover(snapshot)

    assert plans == []


def discovery_service() -> TestDiscoveryService:
    return TestDiscoveryService()
