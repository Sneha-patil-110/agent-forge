
from __future__ import annotations

import re
import secrets
from datetime import UTC, datetime

from backend.core.exceptions import InvalidProjectIdError

PROJECT_ID_PATTERN = re.compile(r"^proj_\d{8}_[0-9a-f]{8}$")


def generate_project_id() -> str:
    date_segment = datetime.now(UTC).strftime("%Y%m%d")
    random_segment = secrets.token_hex(4)

    return f"proj_{date_segment}_{random_segment}"


def validate_project_id(project_id: str) -> str:
    if not isinstance(project_id, str) or not PROJECT_ID_PATTERN.fullmatch(project_id):
        raise InvalidProjectIdError(
            f"Invalid project ID: {project_id!r}. Expected format "
            "'proj_YYYYMMDD_xxxxxxxx' (8 lowercase hex characters).",
            details={"project_id": project_id},
        )

    return project_id
