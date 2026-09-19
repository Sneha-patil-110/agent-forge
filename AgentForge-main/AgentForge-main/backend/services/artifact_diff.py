from __future__ import annotations

import hashlib
from typing import NamedTuple

from backend.state.implementation_state import GeneratedCode


class ArtifactDiff(NamedTuple):
    added_files: list[str]
    modified_files: list[str]
    deleted_files: list[str]
    is_no_effect: bool


def _hash_content(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def compute_artifact_diff(
    before_files: list[GeneratedCode],
    after_files: list[GeneratedCode],
) -> ArtifactDiff:
    before_map = {f.path.replace("\\", "/"): _hash_content(f.content) for f in before_files}
    after_map = {f.path.replace("\\", "/"): _hash_content(f.content) for f in after_files}

    added: list[str] = []
    modified: list[str] = []
    deleted: list[str] = []

    for path, new_hash in after_map.items():
        if path not in before_map:
            added.append(path)
        elif before_map[path] != new_hash:
            modified.append(path)

    for path in before_map:
        if path not in after_map:
            deleted.append(path)

    is_no_effect = len(added) == 0 and len(modified) == 0 and len(deleted) == 0

    return ArtifactDiff(
        added_files=sorted(added),
        modified_files=sorted(modified),
        deleted_files=sorted(deleted),
        is_no_effect=is_no_effect,
    )
