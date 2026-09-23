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
        "openai/gpt-oss-safeguard-20b",
        "qwen/qwen3.8-27b",
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
            # Fail fast instead of the SDK eating tens of seconds in its own
            # backoff -- LLMService's cross-provider fallback is the faster
            # recovery path. max_retries=0 matters specifically for 429s:
            # Groq's client honors the server's Retry-After header (seen:
            # 30-40s) on every retry it's allowed, so even max_retries=1
            # still eats that full wait once. Zero retries skips it entirely.
            "max_retries": 0,
            "request_timeout": 20,
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