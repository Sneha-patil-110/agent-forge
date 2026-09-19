
from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path

from backend.core.workspace import WORKSPACE_ROOT
from backend.core.workspace_containment import resolve_project_destination
from backend.services.artifact_validator import ArtifactValidator
from backend.state.artifact_manifest import ArtifactFile, ArtifactManifest
from backend.state.documentation_state import DocumentationState
from backend.state.implementation_state import ImplementationState
from backend.state.project_state import ProjectState
from backend.tools.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)


class MaterializationService:
    def __init__(
        self,
        tool_registry: ToolRegistry,
        *,
        validator: ArtifactValidator | None = None,
    ) -> None:
        self.tool_registry = tool_registry
        self.validator = validator or ArtifactValidator()

    def materialize(
        self,
        *,
        project: ProjectState,
        implementation: ImplementationState,
        previous_written_files: list[str] | None = None,
    ) -> ImplementationState:
        if not project.output_directory:
            return implementation

        files = [(f.path, f.content, f.language, f.description) for f in implementation.generated_code]
        written_files, file_write_errors = self._write_files(
            output_directory=project.output_directory,
            files=files,
            previous_written_files=previous_written_files,
        )

        out_path = Path(project.output_directory).resolve()
        project_id = out_path.name
        raw_manifest = ArtifactManifest(files=[
            ArtifactFile(path=f.path, content=f.content, language=f.language, description=f.description)
            for f in implementation.generated_code
        ])
        val_res = self.validator.validate_and_normalize(raw_manifest, project_id=project_id)
        norm_map = {orig.path: norm.path for orig, norm in zip(raw_manifest.files, val_res.manifest.files)}

        for code_obj in implementation.generated_code:
            if code_obj.path in norm_map:
                code_obj.path = norm_map[code_obj.path]

        cleaned_written = set()
        for p in written_files:
            clean_p = p.replace("\\", "/").strip("/")
            parts = clean_p.split("/")
            while len(parts) > 1 and parts[0] == project_id:
                parts = parts[1:]
            cleaned_written.add("/".join(parts))

        implementation.written_files = sorted(cleaned_written)
        implementation.file_write_errors = file_write_errors

        return implementation


    def materialize_documentation(
        self,
        *,
        project: ProjectState,
        documentation: DocumentationState,
        previous_written_files: list[str] | None = None,
    ) -> DocumentationState:
        if not project.output_directory:
            return documentation

        files = [(f.path, f.content, "markdown", f.title) for f in documentation.generated_docs]
        written_files, file_write_errors = self._write_files(
            output_directory=project.output_directory,
            files=files,
            previous_written_files=previous_written_files,
        )

        documentation.written_files = written_files
        documentation.file_write_errors = file_write_errors

        return documentation

    def _write_files(
        self,
        *,
        output_directory: str,
        files: list[tuple[str, str, str, str | None]],
        previous_written_files: list[str] | None,
    ) -> tuple[list[str], list[str]]:
        filesystem_tool = self.tool_registry.get("filesystem")
        out_path = Path(output_directory).resolve()
        project_id = out_path.name

        raw_files = [
            ArtifactFile(path=path, content=content, language=lang, description=desc)
            for path, content, lang, desc in files
        ]
        raw_manifest = ArtifactManifest(files=raw_files)

        val_result = self.validator.validate_and_normalize(raw_manifest, project_id=project_id)

        file_write_errors: list[str] = [
            f"{issue.path}: {issue.message}" for issue in val_result.issues
        ]

        written_files: set[str] = set(previous_written_files or [])
        valid_files = val_result.manifest.files

        if not valid_files:
            return sorted(written_files), file_write_errors

        staging_dir = WORKSPACE_ROOT / ".staging" / f"stage_{uuid.uuid4().hex[:12]}"
        staging_dir.mkdir(parents=True, exist_ok=True)

        try:
            for artifact in valid_files:
                try:
                    staging_file = resolve_project_destination(staging_dir, artifact.path)
                    staging_file.parent.mkdir(parents=True, exist_ok=True)
                    staging_file.write_text(artifact.content, encoding="utf-8")
                except Exception as error:
                    file_write_errors.append(f"{artifact.path}: Staging write failed - {error}")

            for artifact in valid_files:
                if any(err.startswith(f"{artifact.path}:") for err in file_write_errors):
                    continue

                staging_file = resolve_project_destination(staging_dir, artifact.path)
                if not staging_file.is_file():
                    continue

                destination = self._resolve_destination(
                    output_directory=output_directory,
                    relative_path=artifact.path,
                )

                result = filesystem_tool.run(
                    operation="write",
                    path=str(destination),
                    content=artifact.content,
                )

                if result.success:
                    written_files.add(artifact.path)
                else:
                    file_write_errors.append(f"{artifact.path}: {result.error}")

        finally:
            if staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)

        logger.info(
            "Materialized %d of %d file(s) to %s",
            len(valid_files) - len(file_write_errors),
            len(files),
            output_directory,
        )

        if file_write_errors:
            logger.warning(
                "%d file(s) failed to write: %s",
                len(file_write_errors),
                file_write_errors,
            )

        return sorted(written_files), file_write_errors

    @staticmethod
    def _validate_relative_path(path: str) -> str | None:
        if not path or not path.strip():
            return "Path cannot be empty."

        candidate = Path(path)
        if candidate.is_absolute():
            return "Path must be relative."

        if ".." in candidate.parts:
            return "Path traversal is not allowed."

        return None

    @staticmethod
    def _resolve_destination(
        *,
        output_directory: str,
        relative_path: str,
    ) -> Path:
        out_path = Path(output_directory).resolve()
        clean_rel = relative_path.replace("\\", "/").strip("/")
        rel_path = Path(clean_rel)

        while len(rel_path.parts) > 1 and rel_path.parts[0] == out_path.name:
            rel_path = Path(*rel_path.parts[1:])

        return resolve_project_destination(out_path, str(rel_path))

