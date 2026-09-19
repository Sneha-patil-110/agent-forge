from __future__ import annotations

from datetime import UTC, datetime

from langchain_core.messages import AIMessage
from pydantic import ValidationError

from backend.agents.base_agent import BaseAgent
from backend.core.exceptions import AgentValidationError
from backend.state.project_state import ProjectState
from backend.state.workflow_state import WorkflowState
from backend.utils.json_utils import parse_json_object


class AnalysisAgent(BaseAgent[ProjectState]):
    @property
    def name(self) -> str:
        return "analysis"

    @property
    def prompt_file(self) -> str:
        return "analysis.md"

    @property
    def model_role(self) -> str:
        return "analysis"

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
    ) -> ProjectState:
        data = parse_json_object(
            response.content,
            agent_name="Analysis",
        )

        try:
            return ProjectState.model_validate(data)

        except ValidationError as error:
            raise AgentValidationError(
                "Analysis Agent output does not match ProjectState.",
                details={"validation_errors": error.errors()},
            ) from error

    def update_state(
        self,
        state: WorkflowState,
        validated_output: ProjectState,
    ) -> WorkflowState:
        validated_output.output_directory = (
            state.project.output_directory
        )

        validated_output.status = (
            state.project.status
        )

        validated_output.created_at = (
            state.project.created_at
        )

        validated_output.updated_at = datetime.now(UTC)

        state.project = validated_output

        return state