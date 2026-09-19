from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_groq import ChatGroq

from backend.core.config import settings
from backend.core.exceptions import ConfigurationError
from backend.llms.base import BaseLLMProvider


class GroqProvider(BaseLLMProvider):
    provider_name = "groq"

    SUPPORTED_MODELS: list[str] = [
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "llama-3.1-8b-instant",
        "llama-3.3-70b-versatile",
        "whisper-large-v3",
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
            supported_models = ", ".join(
                self.SUPPORTED_MODELS
            )

            raise ValueError(
                f"Unsupported Groq model '{model}'. "
                f"Supported models: {supported_models}"
            )

        model_parameters: dict[str, Any] = {
            "model": model,
            "api_key": settings.GROQ_API_KEY,
            "temperature": temperature,
            **kwargs,
        }

        if max_tokens is not None:
            model_parameters["max_tokens"] = max_tokens

        return ChatGroq(
            **model_parameters
        )

    def list_models(
        self,
    ) -> list[str]:
        return self.SUPPORTED_MODELS.copy()

    def validate_credentials(
        self,
    ) -> bool:
        if not settings.GROQ_API_KEY:
            raise ConfigurationError(
                "GROQ_API_KEY is missing from "
                "the environment."
            )

        return True