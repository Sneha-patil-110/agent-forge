from __future__ import annotations

import logging
import time
from typing import TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel

from backend.core.exceptions import AgentForgeException, LLMError
from backend.core.run_context import LLMCallInfo, record_llm_call
from backend.llms.model_registry import ModelRegistry
from backend.services.tracing_service import TracingService


logger = logging.getLogger(__name__)

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class LLMService:
    def __init__(
        self,
        model_registry: ModelRegistry,
        *,
        tracing_service: TracingService | None = None,
    ) -> None:
        self.model_registry = model_registry
        self.tracing_service = tracing_service or TracingService.disabled()

    def invoke(
        self,
        *,
        model_role: str,
        prompt: str,
        context: str,
        response_schema: type[SchemaT] | None = None,
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
        extra_messages: list[BaseMessage] | None = None,
    ) -> AIMessage | SchemaT:

        logger.debug("Invoking model for role '%s'", model_role)

        messages = self._build_messages(
            prompt=prompt,
            context=context,
            extra_messages=extra_messages,
        )

        role_config = getattr(self.model_registry, "config", {}).get(model_role, {})
        candidates = [role_config, *self.model_registry.get_fallback_configs(model_role)]

        failures: list[str] = []

        for attempt_index, candidate_config in enumerate(candidates):
            provider = candidate_config.get("provider")
            model_name = candidate_config.get("model")
            is_fallback = attempt_index > 0

            try:
                model = self._build_model(candidate_config, model_role)
            except AgentForgeException as error:
                failures.append(f"{provider}/{model_name}: {error}")
                continue

            if response_schema is not None:
                model = model.with_structured_output(response_schema)

            if tools:
                try:
                    bind_kwargs = {"tool_choice": tool_choice} if tool_choice is not None else {}
                    model = model.bind_tools(tools, **bind_kwargs)
                except Exception as error:
                    raise LLMError(
                        f"Model for role '{model_role}' does not support tool calling: {error}",
                        details={"model_role": model_role},
                    ) from error

            with self.tracing_service.trace(
                f"llm:{model_role}",
                run_type="llm",
                tags=[tag for tag in (f"agent:{model_role}", f"provider:{provider}" if provider else None) if tag],
                metadata={
                    "agent": model_role,
                    "model_role": model_role,
                    "provider": provider,
                    "model": model_name,
                    "prompt_chars": len(prompt) + len(context),
                    "fallback_attempt": attempt_index,
                },
            ) as run:
                started_at = time.perf_counter()

                try:
                    response = model.invoke(messages)

                    if response_schema is None:
                        _normalize_message_content(response)

                except Exception as error:
                    if is_fallback:
                        logger.warning(
                            "Fallback %d for role '%s' (%s/%s) failed: %s",
                            attempt_index, model_role, provider, model_name, error,
                        )
                    else:
                        logger.warning(
                            "LLM invocation failed for role '%s', trying fallback if configured: %s",
                            model_role, error,
                        )
                    failures.append(f"{provider}/{model_name}: {error}")
                    continue

                if is_fallback:
                    logger.info(
                        "Role '%s' recovered via fallback %d (%s/%s)",
                        model_role, attempt_index, provider, model_name,
                    )

                self.tracing_service.set_outputs(
                    run,
                    {
                        "completion_chars": _content_length(response),
                        "latency_ms": round((time.perf_counter() - started_at) * 1000, 2),
                    },
                )

                record_llm_call(
                    _llm_call_info(
                        response,
                        provider=provider,
                        model=model_name,
                        prompt_characters=len(prompt) + len(context),
                    )
                )

                return response

        raise LLMError(
            f"LLM invocation failed for role '{model_role}' on all "
            f"{len(candidates)} candidate model(s): " + " | ".join(failures),
            details={"model_role": model_role},
        )

    def _build_model(
        self,
        model_config: dict,
        model_role: str,
    ) -> BaseChatModel:
        try:
            return self.model_registry.build_model(model_config, role=model_role)

        except AgentForgeException:
            raise

        except Exception as error:
            raise LLMError(
                f"Failed to load model for role '{model_role}': {error}",
                details={"model_role": model_role},
            ) from error

    @staticmethod
    def _build_messages(
        *,
        prompt: str,
        context: str,
        extra_messages: list[BaseMessage] | None = None,
    ) -> list[BaseMessage]:
        messages: list[BaseMessage] = [
            SystemMessage(content=prompt),
            HumanMessage(content=context),
        ]

        if extra_messages:
            messages.extend(extra_messages)

        return messages


def _normalize_message_content(response: object) -> None:

    content = getattr(response, "content", None)

    if not isinstance(content, list):
        return

    parts: list[str] = []

    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and isinstance(block.get("text"), str):
            parts.append(block["text"])

    response.content = "".join(parts)


def _content_length(response: object) -> int:

    content = getattr(response, "content", None)

    return len(str(content if content is not None else response))


def _llm_call_info(
    response: object,
    *,
    provider: str | None,
    model: str | None,
    prompt_characters: int,
) -> LLMCallInfo:

    usage = getattr(response, "usage_metadata", None) or {}
    response_metadata = getattr(response, "response_metadata", None) or {}

    return LLMCallInfo(
        provider=provider,
        model=model,
        provider_request_id=response_metadata.get("id"),
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
        prompt_characters=prompt_characters,
        response_characters=_content_length(response),
    )
