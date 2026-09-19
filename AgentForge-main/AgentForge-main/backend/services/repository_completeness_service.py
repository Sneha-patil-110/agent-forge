
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from backend.state.architecture_state import ArchitectureState
from backend.state.project_state import ProjectState
from backend.state.repository_snapshot import RepositorySnapshot

_PYTHON_MANIFESTS = ("requirements.txt", "pyproject.toml", "setup.py", "Pipfile")
_NODE_MANIFEST = "package.json"

_PYTHON_DEPENDENCY_FRAMEWORK_HINTS = (
    "fastapi", "django", "flask", "starlette", "tornado", "sanic",
    "sqlalchemy", "pydantic", "celery", "psycopg", "uvicorn",
)
_NODE_DEPENDENCY_FRAMEWORK_HINTS = (
    "next.js", "nextjs", "react", "vue", "angular", "svelte",
    "express", "nestjs", "nest.js", "fastify",
)


class CompletenessIssue(BaseModel):
    kind: str = Field(
        ...,
        description="'empty_repository', 'missing_python_manifest', or 'missing_node_manifest'.",
    )
    message: str


class CompletenessResult(BaseModel):
    is_complete: bool
    issues: list[CompletenessIssue] = Field(default_factory=list)


class RepositoryCompletenessService:
    def check(
        self,
        *,
        project: ProjectState,
        architecture: ArchitectureState,
        snapshot: RepositorySnapshot,
    ) -> CompletenessResult:
        if not snapshot.file_tree:
            return CompletenessResult(
                is_complete=False,
                issues=[
                    CompletenessIssue(
                        kind="empty_repository",
                        message=(
                            "The repository contains no generated files at all -- "
                            "Developer did not produce any implementation."
                        ),
                    )
                ],
            )

        file_set = set(snapshot.file_tree)
        has_py_files = any(f.endswith(".py") for f in file_set)
        has_js_files = any(Path(f).suffix in {".js", ".jsx", ".ts", ".tsx"} for f in file_set)
        has_py_manifest = any(Path(f).name in _PYTHON_MANIFESTS for f in file_set)
        has_node_manifest = any(Path(f).name == _NODE_MANIFEST for f in file_set)

        text_blob = " ".join(
            filter(
                None,
                [
                    project.backend,
                    project.frontend,
                    project.database,
                    project.deployment,
                    *project.tech_stack,
                    architecture.architecture_summary,
                ],
            )
        ).lower()

        issues: list[CompletenessIssue] = []

        if has_py_files and not has_py_manifest:
            matched = next(
                (hint for hint in _PYTHON_DEPENDENCY_FRAMEWORK_HINTS if hint in text_blob),
                None,
            )
            if matched is not None:
                issues.append(
                    CompletenessIssue(
                        kind="missing_python_manifest",
                        message=(
                            f"Python project detected, and the architecture indicates "
                            f"'{matched}' (an external dependency), but no dependency "
                            "manifest (requirements.txt, pyproject.toml, setup.py, or "
                            "Pipfile) was generated."
                        ),
                    )
                )

        if has_js_files and not has_node_manifest:
            matched = next(
                (hint for hint in _NODE_DEPENDENCY_FRAMEWORK_HINTS if hint in text_blob),
                None,
            )
            if matched is not None:
                issues.append(
                    CompletenessIssue(
                        kind="missing_node_manifest",
                        message=(
                            f"Node/JavaScript project detected, and the architecture "
                            f"indicates '{matched}', but no package.json was generated."
                        ),
                    )
                )

        return CompletenessResult(is_complete=not issues, issues=issues)
