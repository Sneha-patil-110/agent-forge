from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.state.planning_state import Milestone, PlanningState, Task


def test_empty_planning_state_is_valid() -> None:
    state = PlanningState()

    assert state.tasks == []


def test_valid_plan_passes() -> None:
    state = PlanningState(
        tasks=[
            Task(id="T1", title="Setup"),
            Task(id="T2", title="Build", dependencies=["T1"], milestone="M1"),
        ],
        milestones=[Milestone(id="M1", title="Release")],
    )

    assert len(state.tasks) == 2


def test_rejects_duplicate_task_ids() -> None:
    with pytest.raises(ValidationError):
        PlanningState(
            tasks=[
                Task(id="T1", title="A"),
                Task(id="T1", title="B"),
            ]
        )


def test_rejects_duplicate_milestone_ids() -> None:
    with pytest.raises(ValidationError):
        PlanningState(
            milestones=[
                Milestone(id="M1", title="A"),
                Milestone(id="M1", title="B"),
            ]
        )


def test_rejects_self_dependency() -> None:
    with pytest.raises(ValidationError):
        PlanningState(tasks=[Task(id="T1", title="A", dependencies=["T1"])])


def test_rejects_unknown_dependency() -> None:
    with pytest.raises(ValidationError):
        PlanningState(tasks=[Task(id="T1", title="A", dependencies=["T99"])])


def test_rejects_circular_dependencies() -> None:
    with pytest.raises(ValidationError):
        PlanningState(
            tasks=[
                Task(id="T1", title="A", dependencies=["T2"]),
                Task(id="T2", title="B", dependencies=["T1"]),
            ]
        )


def test_rejects_unknown_milestone_reference() -> None:
    with pytest.raises(ValidationError):
        PlanningState(
            tasks=[Task(id="T1", title="A", milestone="M-missing")]
        )
