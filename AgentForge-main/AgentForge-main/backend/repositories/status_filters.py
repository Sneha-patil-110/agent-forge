
from __future__ import annotations

from backend.core.exceptions import ValidationError
from backend.state.execution_state import WorkflowStatus

_REAL_STATUSES = frozenset(status.value for status in WorkflowStatus)

_INTERRUPTED_STATUSES = (WorkflowStatus.WAITING_FOR_USER.value,)

_RESUMABLE_STATUSES = (
    WorkflowStatus.INITIALIZED.value,
    WorkflowStatus.RUNNING.value,
    WorkflowStatus.WAITING_FOR_USER.value,
)

_PSEUDO_STATUSES = {
    "resumable": _RESUMABLE_STATUSES,
    "interrupted": _INTERRUPTED_STATUSES,
}


def resolve_status_filter(values: list[str] | None) -> list[str] | None:

    if not values:
        return None

    resolved: set[str] = set()

    for value in values:
        if value in _PSEUDO_STATUSES:
            resolved.update(_PSEUDO_STATUSES[value])
        elif value in _REAL_STATUSES:
            resolved.add(value)
        else:
            raise ValidationError(
                f"Unknown status filter: {value!r}. Expected one of "
                f"{sorted(_REAL_STATUSES | set(_PSEUDO_STATUSES))}."
            )

    return sorted(resolved)
