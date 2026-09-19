from __future__ import annotations

from langchain_core.messages import AIMessage
from pydantic import ValidationError

from backend.agents.base_agent import BaseAgent
from backend.core.exceptions import AgentValidationError
from backend.state.implementation_state import ImplementationState
from backend.state.knowledge_state import KnowledgeCategory
from backend.state.workflow_state import WorkflowState
from backend.utils.json_utils import parse_json_object


class DeveloperAgent(BaseAgent[ImplementationState]):

    @property
    def name(self) -> str:
        return "developer"

    @property
    def prompt_file(self) -> str:
        return "developer.md"

    @property
    def model_role(self) -> str:
        return "developer"

    def build_context(
        self,
        state: WorkflowState,
    ) -> str:
        return self.context_manager.build_context(
            agent_name=self.name,
            state=state,
            mcp_registry=self.mcp_registry,
            mcp_tool_identities=self.mcp_tool_identities,
        )

    def validate(
        self,
        response: AIMessage,
    ) -> ImplementationState:
        data = parse_json_object(
            response.content,
            agent_name="Developer",
        )

        try:
            return ImplementationState.model_validate(data)

        except ValidationError as error:
            raise AgentValidationError(
                "Developer Agent output does not match ImplementationState.",
                details={"validation_errors": error.errors()},
            ) from error

    def update_state(
        self,
        state: WorkflowState,
        validated_output: ImplementationState,
    ) -> WorkflowState:
        previously_completed = set(state.implementation.completed_tasks)
        newly_completed = [
            task_id
            for task_id in validated_output.completed_tasks
            if task_id not in previously_completed
        ]

        state.implementation = validated_output

        task_titles = {task.id: task.title for task in state.planning.tasks}

        for task_id in newly_completed:
            self.knowledge_manager.record(
                state,
                category=KnowledgeCategory.COMPLETED_MILESTONE,
                title=task_titles.get(task_id, task_id),
                content=f"Task {task_id} ({task_titles.get(task_id, 'untitled')}) completed.",
                created_by=self.name,
                source_id=task_id,
            )

        return state