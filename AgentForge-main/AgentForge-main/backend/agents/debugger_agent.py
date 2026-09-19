from __future__ import annotations

from langchain_core.messages import AIMessage
from pydantic import ValidationError

from backend.agents.base_agent import BaseAgent
from backend.core.exceptions import AgentValidationError
from backend.state.debug_state import DebugState
from backend.state.execution_state import RepairTrigger
from backend.state.workflow_state import WorkflowState
from backend.utils.json_utils import parse_json_object


class DebuggerAgent(BaseAgent[DebugState]):

    @property
    def name(self) -> str:
        return "debugger"

    @property
    def prompt_file(self) -> str:
        return "debugger.md"

    @property
    def model_role(self) -> str:
        return "debugger"

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
    ) -> DebugState:
        data = parse_json_object(
            response.content,
            agent_name="Debugger",
        )

        try:
            return DebugState.model_validate(data)

        except ValidationError as error:
            raise AgentValidationError(
                "Debugger Agent output does not match DebugState.",
                details={"validation_errors": error.errors()},
            ) from error

    def update_state(
        self,
        state: WorkflowState,
        validated_output: DebugState,
    ) -> WorkflowState:
        validated_output.attempt_number = (
            state.execution.review_retry_count
            if state.execution.last_repair_trigger == RepairTrigger.REVIEW_FEEDBACK
            else state.execution.test_retry_count
        )

        state.debug = validated_output

        return state
