from __future__ import annotations

import logging

from backend.core.app import Application
from backend.core.workspace import WORKSPACE_ROOT
from backend.state.project_state import ProjectStatus
from backend.state.workflow_state import WorkflowState


logger = logging.getLogger(__name__)


def main() -> None:
    application = Application()

    state = WorkflowState()

    state.project.output_directory = str(
        WORKSPACE_ROOT / "task-manager"
    )

    state.project.project_name = "Task Manager"

    state.project.project_description = (
        "A full stack task management application."
    )

    state.project.objective = (
        "Allow users to create, manage and track tasks."
    )

    state.project.requirements = [
        "User authentication",
        "CRUD tasks",
        "Task categories",
        "Task priorities",
        "Dashboard",
        "Search",
    ]

    state.project.backend = "FastAPI"

    state.project.frontend = "React"

    state.project.database = "PostgreSQL"

    state.project.deployment = "Docker"

    state.project.target_audience = "Students and professionals"

    state.project.tech_stack = [
        "FastAPI",
        "React",
        "PostgreSQL",
        "Docker"
    ]

    state.project.status = ProjectStatus.ANALYZED

    result = application.graph.invoke(state)

    workflow_status = (
        result["execution"]["workflow_status"]
        if isinstance(result, dict)
        else result.execution.workflow_status
    )

    logger.info("Workflow finished with status=%s", workflow_status)


if __name__ == "__main__":
    main()