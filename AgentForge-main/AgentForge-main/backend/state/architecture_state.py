from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class Component(BaseModel):
    name: str = Field(..., description="Component name.")

    description: str = Field(
        ...,
        description="Purpose of the component."
    )

    responsibilities: list[str] = Field(
        default_factory=list,
        description="Responsibilities of the component."
    )

    dependencies: list[str] = Field(
        default_factory=list,
        description="Dependencies of the component."
    )


VALID_HTTP_METHODS = {
    "GET",
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
    "OPTIONS",
    "HEAD",
}


class Endpoint(BaseModel):
    method: str = Field(...)

    path: str = Field(...)

    description: str = Field(...)

    @field_validator("method")
    @classmethod
    def _validate_method(cls, value: str) -> str:
        normalized = value.strip().upper()

        if normalized not in VALID_HTTP_METHODS:
            raise ValueError(
                f"Invalid endpoint method '{value}'. "
                f"Expected one of: {sorted(VALID_HTTP_METHODS)}."
            )

        return normalized


class APIDesign(BaseModel):
    style: str = Field(
        ...,
        description="REST, GraphQL, gRPC, etc."
    )

    endpoints: list[Endpoint] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_unique_endpoints(self) -> APIDesign:
        seen: set[tuple[str, str]] = set()

        for endpoint in self.endpoints:
            key = (endpoint.method, endpoint.path)

            if key in seen:
                raise ValueError(
                    f"Duplicate endpoint: {endpoint.method} {endpoint.path}."
                )

            seen.add(key)

        return self


class DatabaseDesign(BaseModel):
    database_type: str = Field(...)

    entities: list[str] = Field(default_factory=list)

    relationships: list[str] = Field(default_factory=list)


class ArchitectureDecisionStatus(str, Enum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DEPRECATED = "deprecated"
    SUPERSEDED = "superseded"


class ArchitectureDecision(BaseModel):
    id: str = Field(..., description="Unique architecture decision identifier.")

    title: str = Field(...)

    description: str = Field(...)

    status: ArchitectureDecisionStatus = Field(
        default=ArchitectureDecisionStatus.ACCEPTED,
        description="Current status of the architecture decision.",
    )


class Layer(BaseModel):
    name: str = Field(...)

    description: str = Field(...)

    components: list[str] = Field(default_factory=list)


class SystemDesign(BaseModel):
    layers: list[Layer] = Field(default_factory=list)

    communication_flow: str = Field(
        ...,
        description="How the layers communicate with each other."
    )


class ArchitectureState(BaseModel):

    architecture_summary: str | None = Field(
        default=None,
        description="High level architecture overview."
    )

    system_design: SystemDesign | None = Field(
        default=None,
        description="High level description of the architecture."
    )

    folder_structure: dict[str, Any] | None = Field(
        default=None,
        description="Project folder structure as a nested tree."
    )

    api_design: APIDesign | None = Field(
        default=None,
        description="API architecture."
    )

    components: list[Component] = Field(
        default_factory=list,
        description="Major system components."
    )

    database_design: DatabaseDesign | None = Field(
        default=None,
        description="Database architecture."
    )

    design_patterns: list[str] = Field(
        default_factory=list,
        description="Recommended design patterns."
    )

    architecture_decisions: list[ArchitectureDecision] = Field(
        default_factory=list,
        description="Important architecture decisions."
    )

    @model_validator(mode="after")
    def _validate_architecture_state(self) -> ArchitectureState:
        seen_component_names: set[str] = set()

        for component in self.components:
            if component.name in seen_component_names:
                raise ValueError(
                    f"Duplicate component name: '{component.name}'."
                )

            seen_component_names.add(component.name)

        seen_decision_ids: set[str] = set()

        for decision in self.architecture_decisions:
            if decision.id in seen_decision_ids:
                raise ValueError(
                    f"Duplicate architecture decision id: '{decision.id}'."
                )

            seen_decision_ids.add(decision.id)

        return self
