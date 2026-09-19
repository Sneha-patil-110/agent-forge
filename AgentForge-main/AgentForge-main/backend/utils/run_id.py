
from __future__ import annotations

import re
import secrets
from datetime import UTC, datetime

from backend.core.exceptions import InvalidRunIdError

RUN_ID_PATTERN = re.compile(r"^af_\d{8}_[0-9a-f]{8}$")


def generate_run_id() -> str:
    date_segment = datetime.now(UTC).strftime("%Y%m%d")
    random_segment = secrets.token_hex(4)

    return f"af_{date_segment}_{random_segment}"


def validate_run_id(run_id: str) -> str:
    if not isinstance(run_id, str) or not RUN_ID_PATTERN.fullmatch(run_id):
        raise InvalidRunIdError(
            f"Invalid run ID: {run_id!r}. Expected format "
            "'af_YYYYMMDD_xxxxxxxx' (8 lowercase hex characters).",
            details={"run_id": run_id},
        )

    return run_id
