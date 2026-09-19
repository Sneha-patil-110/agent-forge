from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import NamedTuple

from backend.core.exceptions import RepositoryIntegrityError
from backend.state.architecture_state import ArchitectureState
from backend.state.project_state import ProjectState
from backend.state.workflow_state import WorkflowState

logger = logging.getLogger(__name__)


class IntegrityCheckIssue(NamedTuple):
    code: str
    message: str
    path: str | None = None


class IntegrityCheckResult(NamedTuple):
    is_valid: bool
    issues: list[IntegrityCheckIssue]


class RepositoryIntegrityValidator:

    def validate_repository(
        self,
        output_directory: str | None,
        *,
        state: WorkflowState | None = None,
        written_files: list[str] | None = None,
        raise_on_error: bool = False,
    ) -> IntegrityCheckResult:
        issues: list[IntegrityCheckIssue] = []

        if not output_directory:
            issues.append(
                IntegrityCheckIssue(
                    code="NO_OUTPUT_DIRECTORY",
                    message="No project output directory configured.",
                )
            )
            return self._result(issues, raise_on_error)

        root = Path(output_directory).resolve()

        if not root.exists():
            issues.append(
                IntegrityCheckIssue(
                    code="PROJECT_ROOT_MISSING",
                    message=f"Project root directory does not exist: {root}",
                    path=str(root),
                )
            )
            return self._result(issues, raise_on_error)

        if not root.is_dir():
            issues.append(
                IntegrityCheckIssue(
                    code="PROJECT_ROOT_NOT_DIRECTORY",
                    message=f"Project root path is not a directory: {root}",
                    path=str(root),
                )
            )
            return self._result(issues, raise_on_error)

        project_id = root.name
        nested_duplicate = root / project_id
        if nested_duplicate.exists() and nested_duplicate.is_dir():
            issues.append(
                IntegrityCheckIssue(
                    code="DUPLICATE_NESTED_PROJECT_DIRECTORY",
                    message=(
                        f"Detected duplicate nested project directory: {nested_duplicate}. "
                        "Files were incorrectly materialized inside a subfolder matching the project ID."
                    ),
                    path=str(nested_duplicate),
                )
            )

        if written_files:
            for rel_path in written_files:
                file_path = (root / rel_path).resolve()
                if not file_path.exists():
                    issues.append(
                        IntegrityCheckIssue(
                            code="MATERIALIZED_FILE_MISSING",
                            message=f"Materialized file missing on disk: {rel_path}",
                            path=rel_path,
                        )
                    )
                elif not file_path.is_file():
                    issues.append(
                        IntegrityCheckIssue(
                            code="MATERIALIZED_FILE_NOT_A_FILE",
                            message=f"Materialized path is not a regular file: {rel_path}",
                            path=rel_path,
                        )
                    )

        if state is not None:
            self._validate_architecture_spec(root, state, issues)

        return self._result(issues, raise_on_error)

    def _validate_architecture_spec(
        self,
        root: Path,
        state: WorkflowState,
        issues: list[IntegrityCheckIssue],
    ) -> None:
        arch = state.architecture
        project = state.project

        if arch and hasattr(arch, "entrypoints") and isinstance(arch.entrypoints, list):
            for entrypoint in arch.entrypoints:
                if isinstance(entrypoint, str) and entrypoint.strip():
                    ep_path = (root / entrypoint.strip()).resolve()
                    if not ep_path.exists():
                        issues.append(
                            IntegrityCheckIssue(
                                code="MISSING_REQUIRED_ENTRYPOINT",
                                message=f"Required architecture entrypoint is missing: {entrypoint}",
                                path=entrypoint,
                            )
                        )

    def _result(
        self,
        issues: list[IntegrityCheckIssue],
        raise_on_error: bool,
    ) -> IntegrityCheckResult:
        is_valid = len(issues) == 0
        if not is_valid and raise_on_error:
            first_msg = issues[0].message
            raise RepositoryIntegrityError(
                f"Repository integrity validation failed: {first_msg}",
                details={"issues": [i._asdict() for i in issues]},
            )
        return IntegrityCheckResult(is_valid=is_valid, issues=issues)

    def create_snapshot(
        self,
        output_directory: str,
        state: WorkflowState | None = None,
    ) -> RepositorySnapshot:
        from backend.state.repository_snapshot import RepositorySnapshot

        root = Path(output_directory).resolve()
        if not root.exists() or not root.is_dir():
            return RepositorySnapshot(
                project_root=str(root),
                file_tree=[],
                top_level_directories=[],
                project_type="unknown",
            )

        file_tree: list[str] = []
        top_level_dirs: set[str] = set()

        for path in root.rglob("*"):
            rel = path.relative_to(root).as_posix()
            parts = rel.split("/")
            if any(p.startswith(".") or p in {"venv", ".venv", "node_modules", "dist", "build", "coverage", "__pycache__", ".git", ".next", ".staging"} for p in parts):
                continue

            if path.is_dir():
                if len(parts) == 1:
                    top_level_dirs.add(parts[0])
            elif path.is_file():
                file_tree.append(rel)
                if len(parts) > 1:
                    top_level_dirs.add(parts[0])

        file_tree.sort()
        sorted_top_dirs = sorted(top_level_dirs)

        test_dirs: set[str] = set()
        for f in file_tree:
            parts = f.split("/")
            if "tests" in parts or any(p.startswith("test") for p in parts):
                test_dir = "/".join(parts[:-1]) if len(parts) > 1 else "."
                test_dirs.add(test_dir)

        project_type = "unknown"
        entrypoints: list[str] = []

        if state is not None:
            if state.project and state.project.backend:
                project_type = state.project.backend
            elif state.project and state.project.tech_stack:
                project_type = ", ".join(state.project.tech_stack)

            if state.architecture and hasattr(state.architecture, "entrypoints") and state.architecture.entrypoints:
                entrypoints = [str(ep) for ep in state.architecture.entrypoints if ep]

        if not entrypoints:
            for ep in ["backend/app/main.py", "app/main.py", "main.py", "src/index.js", "src/App.tsx"]:
                if ep in file_tree:
                    entrypoints.append(ep)

        return RepositorySnapshot(
            project_root=str(root),
            file_tree=file_tree,
            top_level_directories=sorted_top_dirs,
            project_type=project_type,
            entrypoints=entrypoints,
            known_test_directories=sorted(test_dirs),
            content_hash=self._compute_content_hash(root, file_tree),
        )

    @staticmethod
    def _compute_content_hash(root: Path, file_tree: list[str]) -> str:

        digest = hashlib.sha256()

        for rel_path in file_tree:
            digest.update(rel_path.encode("utf-8"))
            digest.update(b"\x00")
            try:
                digest.update((root / rel_path).read_bytes())
            except OSError:
                digest.update(b"<unreadable>")
            digest.update(b"\x00")

        return digest.hexdigest()

