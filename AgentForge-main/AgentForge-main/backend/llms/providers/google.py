from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI

from backend.core.config import settings
from backend.core.exceptions import ConfigurationError
from backend.llms.base import BaseLLMProvider


class GoogleProvider(BaseLLMProvider):

    provider_name = "google"

    SUPPORTED_MODELS = [
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
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
            raise ValueError(
                f"Unsupported model '{model}'. "
                f"Supported models: {self.SUPPORTED_MODELS}"
            )

        return ChatGoogleGenerativeAI(
            model=model,
            google_api_key=settings.GOOGLE_API_KEY,
            temperature=temperature,
            max_output_tokens=max_tokens,
            **kwargs,
        )

    def list_models(self) -> list[str]:
        return self.SUPPORTED_MODELS

    def validate_credentials(self) -> bool:
        if not settings.GOOGLE_API_KEY:
            raise ConfigurationError(
                "GOOGLE_API_KEY is missing from the environment."
            )

        return True