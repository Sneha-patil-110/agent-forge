from __future__ import annotations

from langchain_core.messages import AIMessage
from pydantic import ValidationError

from backend.agents.base_agent import BaseAgent
from backend.core.exceptions import AgentValidationError
from backend.state.architecture_state import ArchitectureDecisionStatus, ArchitectureState
from backend.state.knowledge_state import KnowledgeCategory
from backend.state.workflow_state import WorkflowState
from backend.utils.json_utils import parse_json_object


class ArchitectAgent(BaseAgent[ArchitectureState]):
    @property
    def name(self) -> str:
        return "architect"

    @property
    def prompt_file(self) -> str:
        return "architect.md"

    @property
    def model_role(self) -> str:
        return "architect"

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
    ) -> ArchitectureState:
        data = parse_json_object(
            response.content,
            agent_name="Architect",
        )

        try:
            return ArchitectureState.model_validate(data)

        except ValidationError as error:
            raise AgentValidationError(
                "Architect Agent output does not match ArchitectureState.",
                details={"validation_errors": error.errors()},
            ) from error

    def update_state(
        self,
        state: WorkflowState,
        validated_output: ArchitectureState,
    ) -> WorkflowState:
        state.architecture = validated_output

        for decision in validated_output.architecture_decisions:
            if decision.status != ArchitectureDecisionStatus.ACCEPTED:
                continue

            self.knowledge_manager.record(
                state,
                category=KnowledgeCategory.ARCHITECTURE_DECISION,
                title=decision.title,
                content=decision.description,
                created_by=self.name,
                source_id=decision.id,
            )

        return state