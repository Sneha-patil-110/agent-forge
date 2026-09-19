from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from backend.core.config import settings
from backend.core.exceptions import ConfigurationError
from backend.llms.base import BaseLLMProvider

_PERPLEXITY_BASE_URL = "https://api.perplexity.ai"


class PerplexityProvider(BaseLLMProvider):
    provider_name = "perplexity"

    SUPPORTED_MODELS: list[str] = [
        "sonar",
        "sonar-pro",
        "sonar-reasoning-pro",
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
                f"Unsupported Perplexity model '{model}'. "
                f"Supported models: {supported_models}"
            )

        return ChatOpenAI(
            model=model,
            api_key=settings.PERPLEXITY_API_KEY,
            base_url=_PERPLEXITY_BASE_URL,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

    def list_models(self) -> list[str]:
        return self.SUPPORTED_MODELS.copy()

    def validate_credentials(self) -> bool:
        if not settings.PERPLEXITY_API_KEY:
            raise ConfigurationError(
                "PERPLEXITY_API_KEY is missing from the environment."
            )

        return True
