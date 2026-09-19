
from __future__ import annotations

import re
from enum import Enum


class PipFailureKind(str, Enum):
    TRANSIENT = "transient"
    DEPENDENCY_ERROR = "dependency_error"
    PYTHON_INCOMPATIBLE = "python_incompatible"


_PYTHON_VERSION_MARKERS = (
    "requires a different python",
)

_MISSING_WHEEL_PATTERN = re.compile(
    r"(?:downloading|using cached)\s+\S+\.tar\.gz", re.IGNORECASE
)
_BUILD_FAILURE_PATTERN = re.compile(
    r"building wheel for .+ did not run successfully"
    r"|building wheel for .+ finished with status ['\"]error['\"]"
    r"|failed building wheel for"
    r"|failed to build \S+"
    r"|error: failed-wheel-build-for-install",
    re.IGNORECASE,
)

_TRANSIENT_MARKERS = (
    "readtimeouterror",
    "connectionerror",
    "newconnectionerror",
    "max retries exceeded",
    "temporary failure in name resolution",
    "could not fetch url",
    "sslerror",
    "connection reset by peer",
    "connection aborted",
    "remote end closed connection",
    "permissiondenied",
    "permission denied",
    "winerror 5",
    "errno 13",
    "no space left on device",
    "disk quota exceeded",
    "httperror 5",
)

_PIP_ERROR_LINE_PATTERN = re.compile(r"^\s*ERROR:.*$", re.MULTILINE)


def classify_pip_failure(*, stdout: str, stderr: str) -> PipFailureKind:
    combined = f"{stdout}\n{stderr}".lower()

    if any(marker in combined for marker in _PYTHON_VERSION_MARKERS):
        return PipFailureKind.PYTHON_INCOMPATIBLE

    if _MISSING_WHEEL_PATTERN.search(combined) and _BUILD_FAILURE_PATTERN.search(combined):
        return PipFailureKind.PYTHON_INCOMPATIBLE

    if any(marker in combined for marker in _TRANSIENT_MARKERS):
        return PipFailureKind.TRANSIENT

    return PipFailureKind.DEPENDENCY_ERROR


def summarize_pip_failure(*, stdout: str, stderr: str) -> str:

    combined = f"{stdout}\n{stderr}"
    error_lines = _PIP_ERROR_LINE_PATTERN.findall(combined)

    if error_lines:
        return " | ".join(line.strip() for line in error_lines[-3:])

    for stream in (stderr, stdout):
        lines = [line.strip() for line in stream.splitlines() if line.strip()]
        if lines:
            return lines[-1]

    return "no output captured"
