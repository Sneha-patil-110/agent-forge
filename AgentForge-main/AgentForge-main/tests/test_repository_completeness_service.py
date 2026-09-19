from __future__ import annotations

from backend.services.repository_completeness_service import RepositoryCompletenessService
from backend.state.architecture_state import ArchitectureState
from backend.state.project_state import ProjectState
from backend.state.repository_snapshot import RepositorySnapshot


def _snapshot(file_tree: list[str]) -> RepositorySnapshot:
    return RepositorySnapshot(project_root="/fake/project", file_tree=file_tree)


def _project(**kwargs) -> ProjectState:
    return ProjectState(**kwargs)


def _architecture(summary: str | None = None) -> ArchitectureState:
    return ArchitectureState(architecture_summary=summary)


def test_empty_repository_is_incomplete() -> None:
    service = RepositoryCompletenessService()

    result = service.check(
        project=_project(), architecture=_architecture(), snapshot=_snapshot([])
    )

    assert result.is_complete is False
    assert result.issues[0].kind == "empty_repository"


def test_zero_dependency_python_cli_without_manifest_is_complete() -> None:

    service = RepositoryCompletenessService()

    result = service.check(
        project=_project(tech_stack=["Python"]),
        architecture=_architecture("A simple standard-library CLI calculator."),
        snapshot=_snapshot(["app.py", "calculator.py", "tests/test_calculator.py"]),
    )

    assert result.is_complete is True
    assert result.issues == []


def test_fastapi_project_missing_manifest_is_incomplete() -> None:
    service = RepositoryCompletenessService()

    result = service.check(
        project=_project(backend="FastAPI"),
        architecture=_architecture("A FastAPI backend with external dependencies."),
        snapshot=_snapshot(["main.py", "routes.py"]),
    )

    assert result.is_complete is False
    assert result.issues[0].kind == "missing_python_manifest"
    assert "fastapi" in result.issues[0].message.lower()


def test_fastapi_project_with_requirements_txt_is_complete() -> None:
    service = RepositoryCompletenessService()

    result = service.check(
        project=_project(backend="FastAPI"),
        architecture=_architecture("A FastAPI backend with external dependencies."),
        snapshot=_snapshot(["main.py", "requirements.txt"]),
    )

    assert result.is_complete is True


def test_fastapi_project_with_pyproject_toml_is_complete() -> None:
    service = RepositoryCompletenessService()

    result = service.check(
        project=_project(backend="FastAPI"),
        architecture=_architecture("A FastAPI backend with external dependencies."),
        snapshot=_snapshot(["main.py", "pyproject.toml"]),
    )

    assert result.is_complete is True


def test_nextjs_project_missing_package_json_is_incomplete() -> None:
    service = RepositoryCompletenessService()

    result = service.check(
        project=_project(frontend="Next.js"),
        architecture=_architecture("A Next.js application."),
        snapshot=_snapshot(["frontend/app/page.tsx", "frontend/app/layout.tsx"]),
    )

    assert result.is_complete is False
    assert result.issues[0].kind == "missing_node_manifest"


def test_nextjs_project_with_package_json_is_complete() -> None:
    service = RepositoryCompletenessService()

    result = service.check(
        project=_project(frontend="Next.js"),
        architecture=_architecture("A Next.js application."),
        snapshot=_snapshot(["frontend/app/page.tsx", "frontend/package.json"]),
    )

    assert result.is_complete is True


def test_plain_node_source_without_framework_hint_is_complete() -> None:

    service = RepositoryCompletenessService()

    result = service.check(
        project=_project(tech_stack=["JavaScript"]),
        architecture=_architecture("A plain script."),
        snapshot=_snapshot(["index.js", "utils.js"]),
    )

    assert result.is_complete is True


def test_documentation_only_repository_is_complete_per_completeness_service() -> None:

    service = RepositoryCompletenessService()

    result = service.check(
        project=_project(),
        architecture=_architecture("A design document collection."),
        snapshot=_snapshot(["README.md", "docs/architecture.md"]),
    )

    assert result.is_complete is True


def test_monorepo_backend_missing_manifest_frontend_fine() -> None:
    service = RepositoryCompletenessService()

    result = service.check(
        project=_project(backend="FastAPI", frontend="Next.js"),
        architecture=_architecture("A FastAPI backend and Next.js frontend."),
        snapshot=_snapshot(
            [
                "backend/main.py",
                "frontend/app/page.tsx",
                "frontend/package.json",
            ]
        ),
    )

    assert result.is_complete is False
    assert len(result.issues) == 1
    assert result.issues[0].kind == "missing_python_manifest"


def test_completeness_trusts_snapshot_not_generated_code() -> None:

    service = RepositoryCompletenessService()

    result = service.check(
        project=_project(backend="FastAPI"),
        architecture=_architecture("A FastAPI backend."),
        snapshot=_snapshot([]),
    )

    assert result.is_complete is False
    assert result.issues[0].kind == "empty_repository"
