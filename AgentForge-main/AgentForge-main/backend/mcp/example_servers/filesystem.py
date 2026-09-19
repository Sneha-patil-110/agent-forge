
from __future__ import annotations

import fnmatch
import json
import os
import stat as stat_module
from pathlib import Path

from fastmcp import FastMCP

from backend.core.workspace import WORKSPACE_ROOT

server = FastMCP("agentforge-filesystem")


def _resolve_path(path: str) -> Path:
    requested = Path(path)
    resolved = requested.resolve() if requested.is_absolute() else (WORKSPACE_ROOT / requested).resolve()

    try:
        resolved.relative_to(WORKSPACE_ROOT.resolve())
    except ValueError as error:
        raise ValueError(
            f"Access denied: '{path}' resolves outside the allowed workspace directory."
        ) from error

    return resolved


def _format_size(size_bytes: int) -> str:
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


@server.tool
def read_text_file(path: str, head: int | None = None, tail: int | None = None) -> str:
    """Read the complete contents of a text file, optionally limited to the first `head` or last `tail` lines."""

    target = _resolve_path(path)

    if not target.is_file():
        raise FileNotFoundError(f"File does not exist: {path}")

    content = target.read_text(encoding="utf-8", errors="replace")

    if head is not None:
        return "\n".join(content.splitlines()[:head])

    if tail is not None:
        return "\n".join(content.splitlines()[-tail:])

    return content


@server.tool
def read_multiple_files(paths: list[str]) -> str:
    """Read the contents of multiple text files at once, returning each labeled and separated by '---'."""

    sections = []

    for path in paths:
        try:
            target = _resolve_path(path)
            content = target.read_text(encoding="utf-8", errors="replace")
            sections.append(f"{path}:\n{content}")
        except Exception as error:
            sections.append(f"{path}: Error - {error}")

    return "\n---\n".join(sections)


@server.tool
def list_directory(path: str) -> str:
    """List the immediate files and directories under the given path, prefixed with [FILE]/[DIR]."""

    target = _resolve_path(path)

    if not target.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {path}")

    lines = []
    for entry in sorted(target.iterdir(), key=lambda p: p.name):
        prefix = "[DIR]" if entry.is_dir() else "[FILE]"
        lines.append(f"{prefix} {entry.name}")

    return "\n".join(lines)


@server.tool
def list_directory_with_sizes(path: str, sortBy: str = "name") -> str:
    """List directory entries along with their sizes, sortable by 'name' or 'size'."""

    target = _resolve_path(path)

    if not target.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {path}")

    entries = []
    for entry in target.iterdir():
        size = entry.stat().st_size if entry.is_file() else 0
        entries.append((entry.name, entry.is_dir(), size))

    if sortBy == "size":
        entries.sort(key=lambda item: item[2], reverse=True)
    else:
        entries.sort(key=lambda item: item[0])

    lines = []
    total_size = 0
    file_count = 0
    dir_count = 0

    for name, is_dir, size in entries:
        prefix = "[DIR]" if is_dir else "[FILE]"
        size_label = "" if is_dir else _format_size(size)
        lines.append(f"{prefix} {name:<40} {size_label:>10}")
        if is_dir:
            dir_count += 1
        else:
            file_count += 1
            total_size += size

    lines.append("")
    lines.append(f"Total: {file_count} files, {dir_count} directories, {_format_size(total_size)}")

    return "\n".join(lines)


def _build_tree(path: Path, exclude_patterns: list[str]) -> dict:
    node: dict = {"name": path.name or str(path), "type": "directory" if path.is_dir() else "file"}

    if path.is_dir():
        children = []
        for entry in sorted(path.iterdir(), key=lambda p: p.name):
            if any(fnmatch.fnmatch(entry.name, pattern) for pattern in exclude_patterns):
                continue
            children.append(_build_tree(entry, exclude_patterns))
        node["children"] = children

    return node


@server.tool
def directory_tree(path: str, excludePatterns: list[str] | None = None) -> str:
    """Return a recursive JSON tree of a directory's contents, skipping any excludePatterns glob matches."""

    target = _resolve_path(path)

    if not target.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {path}")

    tree = _build_tree(target, excludePatterns or [])

    return json.dumps(tree.get("children", []), indent=2)


@server.tool
def search_files(path: str, pattern: str, excludePatterns: list[str] | None = None) -> str:
    """Recursively search for files/directories under path whose name matches the glob pattern."""

    target = _resolve_path(path)
    exclude = excludePatterns or []
    matches = []

    for root, dirs, files in os.walk(target):
        root_path = Path(root)
        dirs[:] = [d for d in dirs if not any(fnmatch.fnmatch(d, ex) for ex in exclude)]

        for name in dirs + files:
            if any(fnmatch.fnmatch(name, ex) for ex in exclude):
                continue
            if fnmatch.fnmatch(name.lower(), f"*{pattern.lower()}*") or fnmatch.fnmatch(name, pattern):
                matches.append(str(root_path / name))

    return "\n".join(sorted(set(matches))) if matches else "No matches found"


@server.tool
def get_file_info(path: str) -> str:
    """Return metadata (size, timestamps, permissions, type) for a file or directory."""

    target = _resolve_path(path)

    if not target.exists():
        raise FileNotFoundError(f"Path does not exist: {path}")

    info = target.stat()
    lines = [
        f"size: {info.st_size}",
        f"created: {info.st_ctime}",
        f"modified: {info.st_mtime}",
        f"accessed: {info.st_atime}",
        f"isDirectory: {target.is_dir()}",
        f"isFile: {target.is_file()}",
        f"permissions: {stat_module.filemode(info.st_mode)}",
    ]

    return "\n".join(lines)


@server.tool
def list_allowed_directories() -> str:
    """Return the list of directories this server is allowed to access."""

    return f"Allowed directories:\n{WORKSPACE_ROOT}"


if __name__ == "__main__":
    server.run()
