import json
import logging
from typing import Any

from langchain_core.messages import AIMessage
from pydantic import BaseModel, ValidationError

from backend.agents.base_agent import BaseAgent
from backend.core.exceptions import (
    AgentOutputEmptyError,
    AgentOutputInvalidJSONError,
    AgentOutputSchemaError,
    AgentOutputTruncatedError,
    AgentValidationError,
)
from backend.state.tester_analysis import TesterAnalysis
from backend.state.workflow_state import WorkflowState
from backend.utils.json_utils import parse_json_object

logger = logging.getLogger(__name__)


class TesterAgent(BaseAgent[TesterAnalysis]):

    __test__ = False

    @property
    def name(self) -> str:
        return "tester"

    @property
    def prompt_file(self) -> str:
        return "tester.md"

    @property
    def model_role(self) -> str:
        return "tester"

    @property
    def response_schema(self) -> type[BaseModel] | None:
        return TesterAnalysis

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
        response: AIMessage | TesterAnalysis | dict[str, Any],
    ) -> TesterAnalysis:
        return self._validate_response(response, allow_recovery=True)

    def _validate_response(
        self,
        response: AIMessage | TesterAnalysis | dict[str, Any],
        *,
        allow_recovery: bool = True,
    ) -> TesterAnalysis:
        if isinstance(response, TesterAnalysis):
            return response

        if isinstance(response, dict):
            try:
                return TesterAnalysis.model_validate(response)
            except ValidationError as err:
                raise AgentOutputSchemaError(
                    "Tester Agent output schema validation failed.",
                    details={"agent": self.name, "validation_errors": err.errors()},
                ) from err

        raw_content = getattr(response, "content", None)
        response_metadata = getattr(response, "response_metadata", None)

        try:
            data = parse_json_object(
                raw_content,
                agent_name="Tester",
                response_metadata=response_metadata,
            )
            return TesterAnalysis.model_validate(data)
        except (AgentOutputInvalidJSONError, AgentOutputSchemaError, ValidationError) as initial_error:
            if allow_recovery and raw_content and str(raw_content).strip():
                logger.warning(
                    "Tester Agent output validation failed (%s); attempting 1-time schema recovery.",
                    initial_error,
                )
                recovered = self._attempt_schema_recovery(
                    raw_content=str(raw_content),
                    error_msg=str(initial_error),
                )
                if recovered:
                    return recovered
                raise AgentOutputSchemaError(
                    f"Tester Agent output schema recovery failed. Initial error: {initial_error}",
                    details={"agent": self.name, "initial_error": str(initial_error)},
                ) from initial_error

            if isinstance(initial_error, AgentValidationError):
                raise initial_error
            raise AgentOutputSchemaError(
                "Tester Agent output does not match the expected analysis schema.",
                details={"agent": self.name, "error": str(initial_error)},
            ) from initial_error

    def _attempt_schema_recovery(
        self,
        *,
        raw_content: str,
        error_msg: str,
    ) -> TesterAnalysis | None:
        correction_prompt = (
            "You are a JSON correction assistant. Your previous response failed schema validation:\n"
            f"Validation Error: {error_msg}\n\n"
            f"Required JSON Schema:\n{json.dumps(TesterAnalysis.model_json_schema(), indent=2)}\n\n"
            "Respond with ONLY a valid JSON object matching the required schema. Do not include commentary."
        )
        correction_context = f"Malformed Previous Response:\n{raw_content[:2000]}"

        try:
            recovery_resp = self.llm_service.invoke(
                model_role=self.model_role,
                prompt=correction_prompt,
                context=correction_context,
                response_schema=TesterAnalysis,
            )
            if isinstance(recovery_resp, TesterAnalysis):
                return recovery_resp
            if isinstance(recovery_resp, dict):
                return TesterAnalysis.model_validate(recovery_resp)

            raw_rec = getattr(recovery_resp, "content", None)
            if raw_rec:
                data = parse_json_object(raw_rec, agent_name="TesterRecovery")
                return TesterAnalysis.model_validate(data)
        except Exception as err:
            logger.warning("Tester Agent schema recovery attempt failed: %s", err)
            return None

        return None

    def update_state(
        self,
        state: WorkflowState,
        validated_output: TesterAnalysis,
    ) -> WorkflowState:
        state.tester_analysis = validated_output

        if validated_output.classification is not None and state.testing.classification is None:
            state.testing.classification = validated_output.classification

        return state
