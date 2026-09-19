from __future__ import annotations

import hashlib
import re
from backend.state.testing_state import TestingState

_LINE_NO_PATTERN = re.compile(r"(?::\d+:?|\bline\s+\d+\b)", re.IGNORECASE)
_TEMP_PATH_PATTERN = re.compile(r"(?:/[^:\s]+|C:\\[^:\s]+)")
_UUID_PATTERN = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)


def compute_failure_fingerprint(testing_state: TestingState, error_message: str | None = None) -> str:
    components: list[str] = []

    if testing_state.status.value:
        components.append(f"status:{testing_state.status.value}")

    if testing_state.failed_tests:
        sorted_test_names = sorted(f.name for f in testing_state.failed_tests)
        components.append(f"failed_tests:{','.join(sorted_test_names)}")

        for f in testing_state.failed_tests:
            raw_msg = (f.message or "") + (f.traceback or "")
            normalized = _normalize_text(raw_msg)
            components.append(f"msg:{normalized}")

    elif error_message:
        components.append(f"error:{_normalize_text(error_message)}")
    elif testing_state.testing_summary:
        components.append(f"summary:{_normalize_text(testing_state.testing_summary)}")

    raw_signature = "|".join(components)
    return hashlib.sha256(raw_signature.encode("utf-8")).hexdigest()[:16]


def _normalize_text(text: str) -> str:
    if not text:
        return ""
    clean = _LINE_NO_PATTERN.sub(":", text)
    clean = _TEMP_PATH_PATTERN.sub("<path>", clean)
    clean = _UUID_PATTERN.sub("<uuid>", clean)
    return " ".join(clean.split())[:500]
