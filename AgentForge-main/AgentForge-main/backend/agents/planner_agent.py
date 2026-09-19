from __future__ import annotations

from langchain_core.messages import AIMessage
from pydantic import ValidationError

from backend.agents.base_agent import BaseAgent
from backend.core.exceptions import AgentValidationError
from backend.state.planning_state import PlanningState
from backend.state.workflow_state import WorkflowState
from backend.utils.json_utils import parse_json_object


class PlannerAgent(BaseAgent[PlanningState]):
    @property
    def name(self) -> str:
        return "planner"

    @property
    def prompt_file(self) -> str:
        return "planner.md"

    @property
    def model_role(self) -> str:
        return "planner"

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
    ) -> PlanningState:
        data = parse_json_object(
            response.content,
            agent_name="Planner",
        )

        try:
            return PlanningState.model_validate(data)

        except ValidationError as error:
            raise AgentValidationError(
                "Planner Agent output does not match PlanningState.",
                details={"validation_errors": error.errors()},
            ) from error

    def update_state(
        self,
        state: WorkflowState,
        validated_output: PlanningState,
    ) -> WorkflowState:
        state.planning = validated_output

        return state