from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class Task(BaseModel):
    id: str = Field(
        ...,
        description="Unique task identifier.",
    )

    title: str = Field(
        ...,
        description="Short task title.",
    )

    description: str | None = Field(
        default=None,
        description="Detailed task description.",
    )

    dependencies: list[str] = Field(
        default_factory=list,
        description=(
            "Task identifiers that must be completed "
            "before this task."
        ),
    )

    milestone: str | None = Field(
        default=None,
        description="Associated milestone identifier.",
    )

    is_completed: bool = Field(
        default=False,
        description="Whether the task has been completed.",
    )


class Milestone(BaseModel):
    id: str = Field(
        ...,
        description="Unique milestone identifier.",
    )

    title: str = Field(
        ...,
        description="Milestone title.",
    )

    description: str | None = Field(
        default=None,
        description="Detailed milestone description.",
    )


class Risk(BaseModel):
    id: str = Field(
        ...,
        description="Unique risk identifier.",
    )

    description: str = Field(
        ...,
        description="Description of the project risk.",
    )

    mitigation: str | None = Field(
        default=None,
        description="Recommended risk mitigation strategy.",
    )


class PlanningState(BaseModel):
    project_summary: str | None = Field(
        default=None,
        description="Concise project summary.",
    )

    implementation_strategy: str | None = Field(
        default=None,
        description="Overall implementation strategy.",
    )

    tasks: list[Task] = Field(
        default_factory=list,
        description="Ordered implementation tasks.",
    )

    milestones: list[Milestone] = Field(
        default_factory=list,
        description="Major project milestones.",
    )

    assumptions: list[str] = Field(
        default_factory=list,
        description="Assumptions made during planning.",
    )

    risks: list[Risk] = Field(
        default_factory=list,
        description="Potential project risks.",
    )

    dependencies: list[str] = Field(
        default_factory=list,
        description="External project dependencies.",
    )

    @model_validator(mode="after")
    def _validate_planning_state(self) -> PlanningState:
        self._validate_unique_ids(self.tasks, "task")
        self._validate_unique_ids(self.milestones, "milestone")
        self._validate_unique_ids(self.risks, "risk")

        task_ids = {task.id for task in self.tasks}
        milestone_ids = {milestone.id for milestone in self.milestones}

        for task in self.tasks:
            if task.id in task.dependencies:
                raise ValueError(
                    f"Task '{task.id}' cannot depend on itself."
                )

            unknown_dependencies = set(task.dependencies) - task_ids

            if unknown_dependencies:
                raise ValueError(
                    f"Task '{task.id}' references unknown "
                    f"dependencies: {sorted(unknown_dependencies)}."
                )

            if task.milestone is not None and task.milestone not in milestone_ids:
                raise ValueError(
                    f"Task '{task.id}' references unknown milestone "
                    f"'{task.milestone}'."
                )

        self._validate_no_cycles(self.tasks)

        return self

    @staticmethod
    def _validate_unique_ids(
        items: list[Task] | list[Milestone] | list[Risk],
        label: str,
    ) -> None:
        seen: set[str] = set()

        for item in items:
            if item.id in seen:
                raise ValueError(
                    f"Duplicate {label} id: '{item.id}'."
                )

            seen.add(item.id)

    @staticmethod
    def _validate_no_cycles(tasks: list[Task]) -> None:

        dependency_map = {task.id: task.dependencies for task in tasks}

        WHITE, GRAY, BLACK = 0, 1, 2
        color = {task_id: WHITE for task_id in dependency_map}

        def visit(task_id: str, path: list[str]) -> None:
            color[task_id] = GRAY

            for dependency_id in dependency_map.get(task_id, []):
                if dependency_id not in color:
                    continue

                if color[dependency_id] == GRAY:
                    cycle = " -> ".join([*path, dependency_id])
                    raise ValueError(
                        f"Circular task dependency detected: {cycle}."
                    )

                if color[dependency_id] == WHITE:
                    visit(dependency_id, [*path, dependency_id])

            color[task_id] = BLACK

        for task_id in dependency_map:
            if color[task_id] == WHITE:
                visit(task_id, [task_id])
