from __future__ import annotations

from typing import Any

from langchain_cerebras import ChatCerebras
from langchain_core.language_models.chat_models import BaseChatModel

from backend.core.config import settings
from backend.core.exceptions import ConfigurationError
from backend.llms.base import BaseLLMProvider


class CerebrasProvider(BaseLLMProvider):
    provider_name = "cerebras"

    SUPPORTED_MODELS: list[str] = [
        "gpt-oss-120b",
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
                f"Unsupported Cerebras model '{model}'. "
                f"Supported models: {supported_models}"
            )

        return ChatCerebras(
            model=model,
            cerebras_api_key=settings.CEREBRAS_API_KEY,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

    def list_models(self) -> list[str]:
        return self.SUPPORTED_MODELS.copy()

    def validate_credentials(self) -> bool:
        if not settings.CEREBRAS_API_KEY:
            raise ConfigurationError(
                "CEREBRAS_API_KEY is missing from the environment."
            )

        return True
