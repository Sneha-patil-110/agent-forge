from __future__ import annotations

from typing import Any

from gradio_client import Client
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from backend.llms.base import BaseLLMProvider

_SPACE_ID = "Qwen/Qwen3-Coder-WebDev"


class QwenCoderChatModel(BaseChatModel):
    """Thin LangChain wrapper around the Qwen3-Coder-WebDev Hugging Face
    Space. No API key needed -- it's a public Gradio Space's `/generate_code`
    endpoint. Returns free-form markdown+code text, NOT structured JSON, so
    this is unsuitable for any AgentForge role that calls
    `with_structured_output()` (architect, developer, reviewer, etc. all do).
    Use it only for prompts expecting plain code/markdown back."""

    system_prompt: str = ""

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        prompt = "\n\n".join(str(m.content) for m in messages)

        client = Client(_SPACE_ID)
        result = client.predict(
            input_value=prompt,
            system_prompt_input_value=self.system_prompt,
            api_name="/generate_code",
        )

        # Response is a tuple of 2 Gradio component-update dicts:
        # (markdown_explanation, code_textbox) -- both {"value": str, "__type__": "update"}
        code_value = ""
        if isinstance(result, (tuple, list)) and len(result) >= 2:
            second = result[1]
            code_value = second.get("value", "") if isinstance(second, dict) else str(second)

        if not code_value and isinstance(result, (tuple, list)) and result:
            first = result[0]
            code_value = first.get("value", "") if isinstance(first, dict) else str(first)

        message = AIMessage(content=code_value)
        return ChatResult(generations=[ChatGeneration(message=message)])

    @property
    def _llm_type(self) -> str:
        return "qwen-coder-webdev"


class QwenCoderProvider(BaseLLMProvider):
    provider_name = "qwen_coder"

    SUPPORTED_MODELS: list[str] = ["qwen3-coder-webdev"]

    def __init__(self) -> None:
        self.validate_credentials()

    def create_chat_model(
        self,
        model: str,
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> BaseChatModel:
        if model not in self.SUPPORTED_MODELS:
            raise ValueError(
                f"Unsupported model '{model}'. "
                f"Supported models: {self.SUPPORTED_MODELS}"
            )

        system_prompt = kwargs.pop("system_prompt", "")
        return QwenCoderChatModel(system_prompt=system_prompt)

    def list_models(self) -> list[str]:
        return self.SUPPORTED_MODELS.copy()

    def supports_structured_output(self) -> bool:
        return False

    def validate_credentials(self) -> bool:
        # No API key: it's a public, anonymous Gradio Space.
        return True
