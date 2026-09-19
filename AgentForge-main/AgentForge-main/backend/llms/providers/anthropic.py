from __future__ import annotations

from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel

from backend.core.config import settings
from backend.core.exceptions import ConfigurationError
from backend.llms.base import BaseLLMProvider

_DEFAULT_MAX_TOKENS = 8192


class AnthropicProvider(BaseLLMProvider):
    provider_name = "anthropic"

    SUPPORTED_MODELS: list[str] = [
        "claude-opus-5",
        "claude-sonnet-5",
        "claude-haiku-4-5-20251001",
    ]

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
            supported_models = ", ".join(self.SUPPORTED_MODELS)

            raise ValueError(
                f"Unsupported Anthropic model '{model}'. "
                f"Supported models: {supported_models}"
            )

        return ChatAnthropic(
            model=model,
            api_key=settings.ANTHROPIC_API_KEY,
            temperature=temperature,
            max_tokens=max_tokens or _DEFAULT_MAX_TOKENS,
            **kwargs,
        )

    def list_models(self) -> list[str]:
        return self.SUPPORTED_MODELS.copy()

    def validate_credentials(self) -> bool:
        if not settings.ANTHROPIC_API_KEY:
            raise ConfigurationError(
                "ANTHROPIC_API_KEY is missing from the environment."
            )

        return True
