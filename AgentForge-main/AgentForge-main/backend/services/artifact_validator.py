from __future__ import annotations

import logging
from pathlib import Path, PureWindowsPath
from typing import NamedTuple

from backend.core.exceptions import PathValidationError
from backend.state.artifact_manifest import ArtifactFile, ArtifactManifest

logger = logging.getLogger(__name__)


class ValidationIssue(NamedTuple):
    path: str
    message: str


class ArtifactValidationResult(NamedTuple):
    is_valid: bool
    manifest: ArtifactManifest
    issues: list[ValidationIssue]


class ArtifactValidator:

    def validate_and_normalize(
        self,
        manifest: ArtifactManifest,
        project_id: str | None = None,
        *,
        raise_on_error: bool = False,
    ) -> ArtifactValidationResult:
        issues: list[ValidationIssue] = []
        normalized_files: list[ArtifactFile] = []
        seen_paths: set[str] = set()

        for artifact in manifest.files:
            raw_path = artifact.path

            if not raw_path or not raw_path.strip():
                issues.append(ValidationIssue(raw_path, "Artifact path cannot be empty."))
                continue

            raw_candidate = Path(raw_path)
            if (
                raw_candidate.is_absolute()
                or raw_candidate.root
                or raw_path.startswith("/")
                or raw_path.startswith("\\")
                or PureWindowsPath(raw_path).is_absolute()
            ):
                issues.append(ValidationIssue(raw_path, f"Path must be relative: {raw_path!r}"))
                continue

            clean_path = raw_path.replace("\\", "/").strip("/")
            candidate = Path(clean_path)

            if ".." in candidate.parts:
                issues.append(ValidationIssue(raw_path, f"Path traversal is prohibited: {raw_path!r}"))
                continue

            if project_id and len(candidate.parts) > 1 and candidate.parts[0] == project_id:
                candidate = Path(*candidate.parts[1:])

            normalized_path_str = candidate.as_posix()

            if normalized_path_str in seen_paths:
                issues.append(
                    ValidationIssue(
                        raw_path,
                        f"Duplicate target path in manifest: {normalized_path_str!r}",
                    )
                )
                continue

            seen_paths.add(normalized_path_str)

            normalized_files.append(
                ArtifactFile(
                    path=normalized_path_str,
                    content=artifact.content,
                    language=artifact.language,
                    description=artifact.description,
                    metadata=artifact.metadata,
                )
            )

        is_valid = len(issues) == 0
        validated_manifest = ArtifactManifest(files=normalized_files)

        if not is_valid and raise_on_error:
            first_msg = issues[0].message if issues else "Manifest validation failed."
            raise PathValidationError(
                f"Artifact manifest validation failed: {first_msg}",
                details={"issues": [i._asdict() for i in issues]},
            )

        return ArtifactValidationResult(
            is_valid=is_valid,
            manifest=validated_manifest,
            issues=issues,
        )
