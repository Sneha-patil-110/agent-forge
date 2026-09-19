from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Generic, TypeVar

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from backend.core.constants import MAX_MCP_TOOL_ROUNDS
from backend.core.exceptions import AgentExecutionError, AgentForgeException, AgentValidationError
from backend.services.context_manager import ContextManager
from backend.services.knowledge_manager import KnowledgeManager
from backend.services.llm_service import LLMService
from backend.services.prompt_service import PromptService
from backend.state.execution_state import AgentType, WorkflowStatus
from backend.state.workflow_state import WorkflowState

if TYPE_CHECKING:
    from backend.mcp.executor import MCPToolExecutor
    from backend.mcp.registry import MCPToolRegistry


logger = logging.getLogger(__name__)

T = TypeVar("T")

_MAX_OUTPUT_REPAIR_ATTEMPTS = 1


class BaseAgent(Generic[T], ABC):
    def __init__(
        self,
        prompt_service: PromptService,
        llm_service: LLMService,
        *,
        mcp_executor: "MCPToolExecutor | None" = None,
        mcp_registry: "MCPToolRegistry | None" = None,
        mcp_tool_identities: list[str] | None = None,
        mcp_fallback_map: dict[str, list[str]] | None = None,
        context_manager: ContextManager | None = None,
        knowledge_manager: KnowledgeManager | None = None,
    ) -> None:
        self.prompt_service = prompt_service
        self.llm_service = llm_service
        self.mcp_executor = mcp_executor
        self.mcp_registry = mcp_registry
        self.mcp_tool_identities = mcp_tool_identities or []
        self.mcp_fallback_map = mcp_fallback_map or {}
        self.context_manager = context_manager or ContextManager()
        self.knowledge_manager = knowledge_manager or KnowledgeManager()

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def prompt_file(self) -> str: ...

    @property
    @abstractmethod
    def model_role(self) -> str:
        pass

    @property
    def response_schema(self) -> type[BaseModel] | None:
        return None

    def run(
        self,
        state: WorkflowState,
    ) -> WorkflowState:
        import uuid
        invocation_id = uuid.uuid4().hex
        self._mark_running(state)
        logger.info("%s agent started (invocation_id=%s)", self.name, invocation_id)

        try:
            prompt = self.load_prompt()

            context = self.build_context(
                state=state,
            )

            validated_output = self._invoke_and_validate(
                prompt=prompt,
                context=context,
            )

            updated_state = self.update_state(
                state=state,
                validated_output=validated_output,
            )

            self._mark_success(
                updated_state,
            )

            logger.info("%s agent completed", self.name)

            return updated_state

        except Exception as error:
            self._mark_failure(
                state=state,
                error=error,
            )

            if isinstance(error, AgentForgeException):
                logger.error("%s agent failed: %s", self.name, error)
                raise

            logger.exception(
                "%s agent failed with an unexpected error", self.name
            )

            raise AgentExecutionError(
                f"{self.name} agent execution failed: {error}",
                details={"agent": self.name},
            ) from error

    def _invoke_and_validate(self, *, prompt: str, context: str) -> T:
        seed_messages: list[BaseMessage] = []

        for attempt in range(_MAX_OUTPUT_REPAIR_ATTEMPTS + 1):
            if self.mcp_executor is not None and self.mcp_tool_identities:
                response = self._invoke_with_tools(
                    prompt=prompt, context=context, seed_messages=seed_messages
                )
            else:
                response = self.llm_service.invoke(
                    model_role=self.model_role,
                    prompt=prompt,
                    context=context,
                    response_schema=self.response_schema,
                    extra_messages=seed_messages or None,
                )

            try:
                return self.validate(response=response)
            except AgentValidationError as error:
                if attempt >= _MAX_OUTPUT_REPAIR_ATTEMPTS:
                    raise

                logger.warning(
                    "%s agent output failed validation (attempt %d/%d): %s -- "
                    "retrying with the error fed back for correction.",
                    self.name,
                    attempt + 1,
                    _MAX_OUTPUT_REPAIR_ATTEMPTS + 1,
                    error,
                )
                seed_messages = [
                    *seed_messages,
                    AIMessage(content=_response_text(response)),
                    HumanMessage(
                        content=(
                            f"That response was invalid: {error}. Return ONLY a corrected, "
                            "complete response that fixes this issue -- no commentary."
                        )
                    ),
                ]

        raise AssertionError("unreachable")

    def _invoke_with_tools(
        self, *, prompt: str, context: str, seed_messages: list[BaseMessage] | None = None
    ) -> AIMessage:
        llm_name_to_identity = {
            self.mcp_registry.get(identity).llm_name: identity
            for identity in self.mcp_tool_identities
        }
        tool_schemas = [
            self.mcp_registry.get(identity).as_langchain_tool_schema()
            for identity in self.mcp_tool_identities
        ]

        extra_messages: list = list(seed_messages) if seed_messages else []
        failed_tool_calls: set[tuple[str, str]] = set()

        for _ in range(MAX_MCP_TOOL_ROUNDS):
            response = self.llm_service.invoke(
                model_role=self.model_role,
                prompt=prompt,
                context=context,
                tools=tool_schemas,
                extra_messages=extra_messages,
            )

            if not getattr(response, "tool_calls", None):
                return response

            extra_messages.append(response)

            for call in response.tool_calls:
                tool_identity = llm_name_to_identity.get(call["name"])
                args_str = json.dumps(call.get("args", {}), sort_keys=True)
                call_key = (tool_identity or call["name"], args_str)

                if call_key in failed_tool_calls:
                    tool_result_text = (
                        f"Tool call '{call['name']}' with arguments {call.get('args')} previously "
                        "failed in this attempt with NOT_FOUND / error. Do not repeat the identical request."
                    )
                elif tool_identity is None:
                    tool_result_text = f"Tool '{call['name']}' is not available to this agent."
                else:
                    try:
                        result = self.mcp_executor.execute(
                            agent=AgentType(self.name),
                            tool_identity=tool_identity,
                            arguments=call["args"],
                        )
                        tool_result_text = result.data or ""
                        if not result.success or "ENOENT" in tool_result_text or "not exist" in tool_result_text:
                            failed_tool_calls.add(call_key)
                    except AgentForgeException as error:
                        failed_tool_calls.add(call_key)
                        tool_result_text = f"Tool call failed: {error}{self._fallback_hint(tool_identity)}"

                extra_messages.append(
                    ToolMessage(content=tool_result_text, tool_call_id=call["id"])
                )


        return self.llm_service.invoke(
            model_role=self.model_role,
            prompt=prompt,
            context=context,
            tools=tool_schemas,
            tool_choice="none",
            extra_messages=extra_messages,
        )

    def _fallback_hint(self, failed_tool_identity: str) -> str:

        server_name = failed_tool_identity.split(".", 1)[0]

        for fallback_server in self.mcp_fallback_map.get(server_name, []):
            has_fallback_tool = any(
                identity.startswith(f"{fallback_server}.")
                for identity in self.mcp_tool_identities
            )

            if has_fallback_tool:
                return f" '{fallback_server}.*' is also available to you and may accomplish the same goal."

        return ""

    def load_prompt(self) -> str:
        try:
            return self.prompt_service.load(
                self.prompt_file
            )

        except FileNotFoundError as error:
            raise FileNotFoundError(
                f"Prompt file '{self.prompt_file}' "
                "was not found in the prompt directory."
            ) from error

    def _mark_running(
        self,
        state: WorkflowState,
    ) -> None:
        state.execution.workflow_status = (
            WorkflowStatus.RUNNING
        )

        state.execution.current_agent = AgentType(
            self.name
        )

        state.execution.current_step = (
            f"Executing {self.name} agent"
        )

        state.execution.error_message = None

    def _mark_success(
        self,
        state: WorkflowState,
    ) -> None:
        state.execution.current_step = (
            f"Completed {self.name} agent"
        )

        if self.name == AgentType.DOCUMENTATION.value:
            state.execution.workflow_status = (
                WorkflowStatus.COMPLETED
            )

            state.execution.completed_at = (
                datetime.now(UTC)
            )

    def _mark_failure(
        self,
        state: WorkflowState,
        error: Exception,
    ) -> None:
        state.execution.workflow_status = (
            WorkflowStatus.FAILED
        )

        state.execution.current_agent = AgentType(
            self.name
        )

        state.execution.current_step = (
            f"Failed during {self.name} agent"
        )

        state.execution.error_message = str(
            error
        )

    @abstractmethod
    def validate(
        self,
        response: AIMessage,
    ) -> T: ...

    @abstractmethod
    def build_context(
        self,
        state: WorkflowState,
    ) -> str: ...

    @abstractmethod
    def update_state(
        self,
        state: WorkflowState,
        validated_output: T,
    ) -> WorkflowState: ...


def _response_text(response: object) -> str:
    content = getattr(response, "content", None)
    return content if isinstance(content, str) else str(response)