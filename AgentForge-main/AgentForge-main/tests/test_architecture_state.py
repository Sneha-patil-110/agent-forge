from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.state.architecture_state import (
    APIDesign,
    ArchitectureDecision,
    ArchitectureState,
    Component,
    Endpoint,
)


def test_empty_architecture_state_is_valid() -> None:
    state = ArchitectureState()

    assert state.components == []


def test_valid_architecture_passes() -> None:
    state = ArchitectureState(
        components=[Component(name="Service", description="Handles work.")],
        architecture_decisions=[
            ArchitectureDecision(id="AD1", title="x", description="y")
        ],
        api_design=APIDesign(
            style="REST",
            endpoints=[Endpoint(method="get", path="/x", description="d")],
        ),
    )

    assert state.api_design.endpoints[0].method == "GET"


def test_rejects_duplicate_component_names() -> None:
    with pytest.raises(ValidationError):
        ArchitectureState(
            components=[
                Component(name="Service", description="a"),
                Component(name="Service", description="b"),
            ]
        )


def test_rejects_duplicate_decision_ids() -> None:
    with pytest.raises(ValidationError):
        ArchitectureState(
            architecture_decisions=[
                ArchitectureDecision(id="AD1", title="a", description="a"),
                ArchitectureDecision(id="AD1", title="b", description="b"),
            ]
        )


def test_rejects_invalid_endpoint_method() -> None:
    with pytest.raises(ValidationError):
        Endpoint(method="FETCH", path="/x", description="d")


def test_rejects_duplicate_endpoint_method_and_path() -> None:
    with pytest.raises(ValidationError):
        APIDesign(
            style="REST",
            endpoints=[
                Endpoint(method="GET", path="/x", description="a"),
                Endpoint(method="GET", path="/x", description="b"),
            ],
        )


def test_allows_same_path_with_different_methods() -> None:
    design = APIDesign(
        style="REST",
        endpoints=[
            Endpoint(method="GET", path="/x", description="a"),
            Endpoint(method="POST", path="/x", description="b"),
        ],
    )

    assert len(design.endpoints) == 2
