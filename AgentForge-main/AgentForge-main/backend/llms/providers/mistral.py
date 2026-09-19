from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from backend.core.config import settings
from backend.core.exceptions import ConfigurationError
from backend.llms.base import BaseLLMProvider

_MISTRAL_BASE_URL = "https://api.mistral.ai/v1"


class MistralProvider(BaseLLMProvider):
    provider_name = "mistral"

    SUPPORTED_MODELS: list[str] = [
        "codestral-latest",
        "mistral-large-latest",
        "mistral-medium-latest",
        "mistral-small-latest",
    ]

    def __init__(self) -> None:
        self.validate_credentials()

    def create_chat_model(
        self,
        model: str,
        *,
        temperature: float = 0.1,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> BaseChatModel:
        if model not in self.SUPPORTED_MODELS:
            supported_models = ", ".join(self.SUPPORTED_MODELS)

            raise ValueError(
                f"Unsupported Mistral model '{model}'. "
                f"Supported models: {supported_models}"
            )

        return ChatOpenAI(
            model=model,
            api_key=settings.MISTRAL_API_KEY,
            base_url=_MISTRAL_BASE_URL,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

    def list_models(self) -> list[str]:
        return self.SUPPORTED_MODELS.copy()

    def validate_credentials(self) -> bool:
        if not settings.MISTRAL_API_KEY:
            raise ConfigurationError(
                "MISTRAL_API_KEY is missing from the environment."
            )

        return True
