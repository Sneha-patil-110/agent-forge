from __future__ import annotations

from pathlib import Path

from backend.core.exceptions import WorkspaceContainmentError
from backend.core.workspace import WORKSPACE_ROOT


def resolve_project_destination(project_root: str | Path, relative_path: str) -> Path:
    if not relative_path or not relative_path.strip():
        raise WorkspaceContainmentError("Relative path cannot be empty.")

    root = Path(project_root).resolve()

    candidate = Path(relative_path)
    if candidate.is_absolute() or candidate.root:
        raise WorkspaceContainmentError(f"Path must be relative, got absolute: {relative_path!r}")

    if ".." in candidate.parts:
        raise WorkspaceContainmentError(f"Path traversal ('..') is not permitted: {relative_path!r}")

    destination = (root / candidate).resolve()

    try:
        destination.relative_to(root)
    except ValueError as error:
        raise WorkspaceContainmentError(
            f"Destination path {relative_path!r} escapes project root {root}: {error}"
        ) from error

    return destination
