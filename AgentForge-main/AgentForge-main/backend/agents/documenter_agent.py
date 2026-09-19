from __future__ import annotations

from langchain_core.messages import AIMessage
from pydantic import ValidationError

from backend.agents.base_agent import BaseAgent
from backend.core.exceptions import AgentValidationError
from backend.state.documentation_state import DocumentationState
from backend.state.workflow_state import WorkflowState
from backend.utils.json_utils import parse_json_object


class DocumentationAgent(BaseAgent[DocumentationState]):
    @property
    def name(self) -> str:
        return "documentation"

    @property
    def prompt_file(self) -> str:
        return "documentation.md"

    @property
    def model_role(self) -> str:
        return "documentation"

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
    ) -> DocumentationState:
        data = parse_json_object(
            response.content,
            agent_name="Documentation",
        )

        try:
            return DocumentationState.model_validate(data)

        except ValidationError as error:
            raise AgentValidationError(
                "Documentation Agent output does not match DocumentationState.",
                details={
                    "validation_errors": error.errors(),
                    "parsed_response": data,
                },
            ) from error

    def update_state(
        self,
        state: WorkflowState,
        validated_output: DocumentationState,
    ) -> WorkflowState:
        state.documentation = validated_output

        return state