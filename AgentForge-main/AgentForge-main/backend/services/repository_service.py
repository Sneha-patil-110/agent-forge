
from __future__ import annotations

import hashlib
import io
import logging
import re
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from backend.core.exceptions import (
    InvalidRepositoryPathError,
    RepositoryConflictError,
    RepositoryFileNotTextError,
    RepositoryPathAlreadyExistsError,
    RepositoryPathNotFoundError,
)
from backend.events.dispatcher import EventDispatcher
from backend.events.event_types import EventType, WorkflowEvent
from backend.repositories.documentation_repository import DocumentationRepository
from backend.repositories.file_version_repository import FileVersionRepository
from backend.services.materialization_service import MaterializationService
from backend.state.workflow_state import WorkflowState
from backend.tools.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)

_RESERVED_WINDOWS_NAMES = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}
_LANGUAGE_BY_EXTENSION = {
    "py": "python", "js": "javascript", "jsx": "javascript", "ts": "typescript",
    "tsx": "typescript", "json": "json", "md": "markdown", "mdx": "markdown",
    "html": "html", "css": "css", "scss": "scss", "yml": "yaml", "yaml": "yaml",
    "toml": "toml", "sql": "sql", "sh": "shell", "bash": "shell", "go": "go",
    "rs": "rust", "java": "java", "rb": "ruby", "php": "php", "c": "c",
    "cpp": "cpp", "h": "c", "xml": "xml",
}


@dataclass
class RepoFileNode:
    type: str
    name: str
    path: str
    size_bytes: int | None = None
    children: list["RepoFileNode"] = field(default_factory=list)


@dataclass
class FileMetadata:
    path: str
    size_bytes: int
    language: str
    last_modified: datetime
    generated_by_ai: bool
    last_edited_by: str | None
    agent: str | None


@dataclass
class SearchMatch:
    path: str
    line: int | None
    snippet: str | None


def validate_repository_path(path: str) -> str:

    if not path or not path.strip():
        raise InvalidRepositoryPathError("Path cannot be empty.")

    candidate = Path(path)

    if candidate.is_absolute() or candidate.root:
        raise InvalidRepositoryPathError("Path must be relative.")

    if ".." in candidate.parts:
        raise InvalidRepositoryPathError("Path traversal is not allowed.")

    for segment in candidate.parts:
        stripped = segment.strip(" .")

        if not stripped:
            raise InvalidRepositoryPathError(f"Invalid path segment: {segment!r}.")

        if len(segment) > 255:
            raise InvalidRepositoryPathError(f"Path segment too long: {segment!r}.")

        if re.search(r'[<>:"|?*\x00-\x1f]', segment):
            raise InvalidRepositoryPathError(f"Path segment contains invalid characters: {segment!r}.")

        name_without_extension = stripped.split(".")[0].lower()

        if name_without_extension in _RESERVED_WINDOWS_NAMES:
            raise InvalidRepositoryPathError(f"'{segment}' is a reserved filename.")

    return path


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def language_from_path(path: str) -> str:
    extension = path.lower().rsplit(".", 1)[-1] if "." in path else ""
    return _LANGUAGE_BY_EXTENSION.get(extension, "plaintext")


class RepositoryService:
    def __init__(
        self,
        *,
        tool_registry: ToolRegistry,
        event_dispatcher: EventDispatcher,
        db_session_factory,
        materialization_service: MaterializationService | None = None,
    ) -> None:
        self.tool_registry = tool_registry
        self.event_dispatcher = event_dispatcher
        self.db_session_factory = db_session_factory
        self.materialization_service = materialization_service

    def ensure_materialized(self, *, run_id: str, state: WorkflowState, output_directory: str) -> None:
        """Rebuild the workspace directory if the app container's local disk lost it.

        Generated code/doc content lives in `WorkflowState` (durable in Postgres,
        see RunService), so it can always be replayed back to disk. Anything
        edited afterward is layered on top from FileVersionRecord, which already
        stores full content for every user edit.
        """
        if Path(output_directory).exists() or self.materialization_service is None:
            return

        try:
            self.materialization_service.materialize(
                project=state.project, implementation=state.implementation
            )
            self.materialization_service.materialize_documentation(
                project=state.project, documentation=state.documentation
            )
            self._restore_latest_edits(run_id, output_directory)
            logger.warning(
                "Rehydrated workspace for run %s from durable storage after local files were missing.",
                run_id,
            )
        except Exception:
            logger.warning("Failed to rehydrate workspace for run %s.", run_id, exc_info=True)

    def _restore_latest_edits(self, run_id: str, output_directory: str) -> None:
        if self.db_session_factory is None:
            return

        latest_by_path: dict[str, str] = {}

        with self.db_session_factory() as session:
            for record in FileVersionRepository(session).list_for_run(run_id):
                latest_by_path[record.path] = record.content

        for path, content in latest_by_path.items():
            try:
                validate_repository_path(path)
                self._write(output_directory, path, content)
            except Exception:
                logger.warning(
                    "Failed to restore edited file %s for run %s during rehydration.",
                    path,
                    run_id,
                    exc_info=True,
                )

    def get_tree(self, output_directory: str) -> list[RepoFileNode]:
        root = Path(output_directory).resolve()

        if not root.exists():
            return []

        return self._scan(root, root)

    def build_zip_archive(self, output_directory: str) -> bytes:
        root = Path(output_directory).resolve()

        if not root.exists():
            raise RepositoryPathNotFoundError("No generated files are available for this run yet.")

        archive_name = root.name
        buffer = io.BytesIO()

        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for file_path in sorted(root.rglob("*")):
                if not file_path.is_file():
                    continue

                relative = file_path.relative_to(root)
                archive.write(file_path, arcname=str(Path(archive_name) / relative))

        return buffer.getvalue()

    def _scan(self, root: Path, current: Path) -> list[RepoFileNode]:
        nodes: list[RepoFileNode] = []

        if not current.exists() or not current.is_dir():
            return nodes

        for entry in sorted(current.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
            try:
                entry.resolve().relative_to(root)
            except (ValueError, OSError):
                continue

            relative = str(entry.relative_to(root)).replace("\\", "/")

            if entry.is_dir():
                nodes.append(
                    RepoFileNode(
                        type="folder", name=entry.name, path=relative, children=self._scan(root, entry)
                    )
                )
            else:
                nodes.append(
                    RepoFileNode(
                        type="file", name=entry.name, path=relative, size_bytes=entry.stat().st_size
                    )
                )

        return nodes

    def read_file(self, output_directory: str, path: str) -> str:
        validate_repository_path(path)
        resolved = self._resolve(output_directory, path)

        if not resolved.is_file():
            raise RepositoryPathNotFoundError(f"File not found: {path}")

        try:
            return resolved.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            raise RepositoryFileNotTextError(f"'{path}' is not a text file.") from error

    def get_metadata(
        self,
        output_directory: str,
        path: str,
        *,
        run_id: str,
        documentation_paths: frozenset[str] = frozenset(),
        developer_written_paths: frozenset[str] = frozenset(),
    ) -> FileMetadata:
        validate_repository_path(path)
        resolved = self._resolve(output_directory, path)

        if not resolved.is_file():
            raise RepositoryPathNotFoundError(f"File not found: {path}")

        stat = resolved.stat()
        last_edited_by = None

        if self.db_session_factory is not None:
            try:
                with self.db_session_factory() as session:
                    versions = FileVersionRepository(session).list_for_file(run_id, path)
                    if versions:
                        last_edited_by = versions[-1].edited_by
            except Exception:
                logger.warning("Could not load version history for metadata on %s", path, exc_info=True)

        if path in documentation_paths:
            agent = "documentation"
        elif path in developer_written_paths:
            agent = "developer"
        else:
            agent = None

        return FileMetadata(
            path=path,
            size_bytes=stat.st_size,
            language=language_from_path(path),
            last_modified=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
            generated_by_ai=last_edited_by is None,
            last_edited_by=last_edited_by,
            agent=agent,
        )

    def get_documentation_metadata(self, run_id: str) -> dict[str, dict]:

        if self.db_session_factory is None:
            return {}

        try:
            with self.db_session_factory() as session:
                records = DocumentationRepository(session).list_for_run(run_id)
                return {
                    record.path: {
                        "generating_agent": record.generating_agent,
                        "status": record.status,
                        "created_at": record.created_at,
                        "updated_at": record.updated_at,
                    }
                    for record in records
                }
        except Exception:
            logger.warning("Could not load documentation metadata for run %s", run_id, exc_info=True)
            return {}

    def search(
        self,
        output_directory: str,
        *,
        query: str,
        mode: str,
        language: str | None,
        limit: int = 100,
    ) -> list[SearchMatch]:
        tree = self.get_tree(output_directory)
        needle = query.lower()

        if mode == "content":
            files = _flatten(tree)

            if language:
                files = [f for f in files if language_from_path(f.path) == language]

            root = Path(output_directory).resolve()
            matches: list[SearchMatch] = []

            for file_node in files:
                try:
                    content = (root / file_node.path).read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue

                for line_number, line in enumerate(content.split("\n"), start=1):
                    if needle in line.lower():
                        matches.append(
                            SearchMatch(path=file_node.path, line=line_number, snippet=line.strip()[:160])
                        )
                        if len(matches) >= limit:
                            return matches

            return matches

        nodes = _flatten_all(tree)

        if language:
            nodes = [n for n in nodes if n.type == "folder" or language_from_path(n.path) == language]

        if mode == "fuzzy":
            scored: list[tuple[float, RepoFileNode]] = []

            for node in nodes:
                score = _fuzzy_score(needle, node.path.lower())
                if score is not None:
                    scored.append((score, node))

            scored.sort(key=lambda pair: pair[0], reverse=True)
            return [SearchMatch(path=node.path, line=None, snippet=None) for _, node in scored[:limit]]

        matches = []

        for node in nodes:
            if needle in node.name.lower() or needle in node.path.lower():
                matches.append(SearchMatch(path=node.path, line=None, snippet=None))
                if len(matches) >= limit:
                    break

        return matches


    def create_file(
        self, *, run_id: str, output_directory: str, path: str, content: str, actor: str
    ) -> None:
        validate_repository_path(path)
        resolved = self._resolve(output_directory, path)

        if resolved.exists():
            raise RepositoryPathAlreadyExistsError(f"File already exists: {path}")

        self._write(output_directory, path, content)
        self._snapshot(run_id, path, content, source="user_edit", edited_by=actor)
        self._emit(EventType.FILE_CREATED, run_id, path)

    def update_file(
        self,
        *,
        run_id: str,
        output_directory: str,
        path: str,
        content: str,
        actor: str,
        expected_version: str | None = None,
    ) -> None:
        validate_repository_path(path)
        resolved = self._resolve(output_directory, path)

        if not resolved.is_file():
            raise RepositoryPathNotFoundError(f"File not found: {path}")

        try:
            previous_content = resolved.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            previous_content = None

        if previous_content is not None and expected_version is not None:
            current_hash = _content_hash(previous_content)
            if current_hash != expected_version:
                raise RepositoryConflictError(
                    f"'{path}' changed since it was last read. Reload before saving."
                )

        if previous_content is not None and not self._has_version_history(run_id, path):
            self._snapshot(run_id, path, previous_content, source="generated", edited_by=None)

        self._write(output_directory, path, content)
        self._snapshot(run_id, path, content, source="user_edit", edited_by=actor)
        self._emit(EventType.FILE_MODIFIED, run_id, path)

    def delete_file(self, *, run_id: str, output_directory: str, path: str) -> None:
        validate_repository_path(path)
        resolved = self._resolve(output_directory, path)

        if not resolved.is_file():
            raise RepositoryPathNotFoundError(f"File not found: {path}")

        self.tool_registry.get("filesystem").run(operation="delete", path=str(resolved))
        self._delete_documentation_record(run_id, path)
        self._emit(EventType.FILE_DELETED, run_id, path)

    def rename_file(self, *, run_id: str, output_directory: str, path: str, new_name: str) -> str:
        new_path = str(Path(path).parent / new_name).replace("\\", "/")
        if new_path.startswith("./"):
            new_path = new_path[2:]

        self._move(run_id, output_directory, path, new_path, event_type=EventType.FILE_RENAMED)
        return new_path

    def move_file(self, *, run_id: str, output_directory: str, path: str, destination: str) -> None:
        self._move(run_id, output_directory, path, destination, event_type=EventType.FILE_MODIFIED)

    def duplicate_file(
        self, *, run_id: str, output_directory: str, path: str, destination: str, actor: str
    ) -> None:
        validate_repository_path(path)
        validate_repository_path(destination)
        source = self._resolve(output_directory, path)
        target = self._resolve(output_directory, destination)

        if not source.is_file():
            raise RepositoryPathNotFoundError(f"File not found: {path}")

        if target.exists():
            raise RepositoryPathAlreadyExistsError(f"File already exists: {destination}")

        self.tool_registry.get("filesystem").run(
            operation="copy", path=str(source), destination=str(target)
        )

        try:
            duplicated_content = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            duplicated_content = None

        if duplicated_content is not None:
            self._snapshot(run_id, destination, duplicated_content, source="user_edit", edited_by=actor)

        self._emit(EventType.FILE_CREATED, run_id, destination)

    def create_folder(self, *, run_id: str, output_directory: str, path: str) -> None:
        validate_repository_path(path)
        resolved = self._resolve(output_directory, path)

        if resolved.exists():
            raise RepositoryPathAlreadyExistsError(f"Folder already exists: {path}")

        self.tool_registry.get("filesystem").run(operation="mkdir", path=str(resolved))
        self._emit(EventType.FOLDER_CREATED, run_id, path)

    def delete_folder(self, *, run_id: str, output_directory: str, path: str) -> None:
        validate_repository_path(path)
        resolved = self._resolve(output_directory, path)

        if not resolved.is_dir():
            raise RepositoryPathNotFoundError(f"Folder not found: {path}")

        self.tool_registry.get("filesystem").run(operation="rmdir", path=str(resolved))
        self._emit(EventType.FOLDER_DELETED, run_id, path)

    def rename_folder(self, *, run_id: str, output_directory: str, path: str, new_name: str) -> str:
        new_path = str(Path(path).parent / new_name).replace("\\", "/")
        if new_path.startswith("./"):
            new_path = new_path[2:]

        self._move_folder(run_id, output_directory, path, new_path)
        return new_path

    def move_folder(self, *, run_id: str, output_directory: str, path: str, destination: str) -> None:
        self._move_folder(run_id, output_directory, path, destination)


    def _resolve(self, output_directory: str, path: str) -> Path:
        root = Path(output_directory).resolve()
        resolved = (root / path).resolve()

        try:
            resolved.relative_to(root)
        except ValueError as error:
            raise InvalidRepositoryPathError(f"Path escapes the workspace: {path!r}.") from error

        return resolved

    def _write(self, output_directory: str, path: str, content: str) -> None:
        destination = self._resolve(output_directory, path)
        self.tool_registry.get("filesystem").run(operation="write", path=str(destination), content=content)

    def _move(
        self, run_id: str, output_directory: str, path: str, destination: str, *, event_type: EventType
    ) -> None:
        validate_repository_path(path)
        validate_repository_path(destination)
        source = self._resolve(output_directory, path)
        target = self._resolve(output_directory, destination)

        if not source.is_file():
            raise RepositoryPathNotFoundError(f"File not found: {path}")

        if target.exists():
            raise RepositoryPathAlreadyExistsError(f"File already exists: {destination}")

        self.tool_registry.get("filesystem").run(
            operation="move", path=str(source), destination=str(target)
        )
        self._rename_documentation_record(run_id, path, destination)
        self._emit(event_type, run_id, destination, metadata={"previous_path": path})

    def _move_folder(self, run_id: str, output_directory: str, path: str, destination: str) -> None:
        validate_repository_path(path)
        validate_repository_path(destination)
        source = self._resolve(output_directory, path)
        target = self._resolve(output_directory, destination)

        if not source.is_dir():
            raise RepositoryPathNotFoundError(f"Folder not found: {path}")

        if target.exists():
            raise RepositoryPathAlreadyExistsError(f"Folder already exists: {destination}")

        self.tool_registry.get("filesystem").run(
            operation="move", path=str(source), destination=str(target)
        )
        self._emit(EventType.FOLDER_CREATED, run_id, destination, metadata={"previous_path": path})

    def _delete_documentation_record(self, run_id: str, path: str) -> None:
        if self.db_session_factory is None:
            return

        try:
            with self.db_session_factory() as session:
                DocumentationRepository(session).delete(run_id, path)
                session.commit()
        except Exception:
            logger.warning(
                "Failed to remove documentation record for %s on run %s", path, run_id, exc_info=True
            )

    def _rename_documentation_record(self, run_id: str, old_path: str, new_path: str) -> None:
        if self.db_session_factory is None:
            return

        try:
            with self.db_session_factory() as session:
                DocumentationRepository(session).rename(run_id, old_path, new_path)
                session.commit()
        except Exception:
            logger.warning(
                "Failed to update documentation record for %s -> %s on run %s",
                old_path,
                new_path,
                run_id,
                exc_info=True,
            )

    def _has_version_history(self, run_id: str, path: str) -> bool:
        if self.db_session_factory is None:
            return True

        try:
            with self.db_session_factory() as session:
                return bool(FileVersionRepository(session).list_for_file(run_id, path))
        except Exception:
            logger.warning("Could not check version history for %s on run %s", path, run_id, exc_info=True)
            return True

    def _snapshot(self, run_id: str, path: str, content: str, *, source: str, edited_by: str | None) -> None:
        if self.db_session_factory is None:
            return

        try:
            with self.db_session_factory() as session:
                FileVersionRepository(session).add(
                    run_id=run_id,
                    path=path,
                    content=content,
                    source=source,
                    edited_by=edited_by,
                    created_at=datetime.now(UTC),
                )
                session.commit()
        except Exception:
            logger.warning("Failed to snapshot version for %s on run %s", path, run_id, exc_info=True)

    def _emit(
        self, event_type: EventType, run_id: str, path: str, *, metadata: dict | None = None
    ) -> None:
        self.event_dispatcher.emit(
            WorkflowEvent(
                event_type=event_type,
                run_id=run_id,
                metadata={"path": path, **(metadata or {})},
            )
        )


def _flatten(nodes: list[RepoFileNode]) -> list[RepoFileNode]:
    result: list[RepoFileNode] = []

    for node in nodes:
        if node.type == "file":
            result.append(node)
        else:
            result.extend(_flatten(node.children))

    return result


def _flatten_all(nodes: list[RepoFileNode]) -> list[RepoFileNode]:

    result: list[RepoFileNode] = []

    for node in nodes:
        result.append(node)

        if node.type == "folder":
            result.extend(_flatten_all(node.children))

    return result


def _fuzzy_score(needle: str, haystack: str) -> float | None:

    if not needle:
        return 0.0

    haystack_index = 0
    match_positions: list[int] = []

    for char in needle:
        found_at = haystack.find(char, haystack_index)

        if found_at == -1:
            return None

        match_positions.append(found_at)
        haystack_index = found_at + 1

    span = match_positions[-1] - match_positions[0] + 1

    return len(needle) / span
