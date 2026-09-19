from __future__ import annotations

from langchain_core.messages import AIMessage
from pydantic import ValidationError

from backend.agents.base_agent import BaseAgent
from backend.core.exceptions import AgentValidationError
from backend.state.knowledge_state import KnowledgeCategory
from backend.state.review_state import ReviewState
from backend.state.workflow_state import WorkflowState
from backend.utils.json_utils import parse_json_object


class ReviewerAgent(BaseAgent[ReviewState]):
    @property
    def name(self) -> str:
        return "reviewer"

    @property
    def prompt_file(self) -> str:
        return "reviewer.md"

    @property
    def model_role(self) -> str:
        return "reviewer"

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
    ) -> ReviewState:
        data = parse_json_object(
            response.content,
            agent_name="Reviewer",
        )

        try:
            return ReviewState.model_validate(data)

        except ValidationError as error:
            raise AgentValidationError(
                "Reviewer Agent output does not match ReviewState.",
                details={"validation_errors": error.errors()},
            ) from error

    def update_state(
        self,
        state: WorkflowState,
        validated_output: ReviewState,
    ) -> WorkflowState:
        validated_output.attempt_number = state.execution.review_retry_count + 1

        state.review = validated_output

        for recommendation in validated_output.recommendations:
            self.knowledge_manager.record(
                state,
                category=KnowledgeCategory.CODING_STANDARD,
                title="Review Recommendation",
                content=recommendation,
                created_by=self.name,
            )

        return state