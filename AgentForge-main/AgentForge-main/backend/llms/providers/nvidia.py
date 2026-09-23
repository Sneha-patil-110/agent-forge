from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_nvidia_ai_endpoints import ChatNVIDIA

from backend.core.config import settings
from backend.core.exceptions import ConfigurationError
from backend.llms.base import BaseLLMProvider


class NvidiaProvider(BaseLLMProvider):
    provider_name = "nvidia"

    SUPPORTED_MODELS: list[str] = [
        "openai/gpt-oss-20b",
        "openai/gpt-oss-120b",
        "meta/llama-3.3-70b-instruct",
        "qwen/qwen3-coder-480b-a35b-instruct",
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
                f"Unsupported NVIDIA NIM model '{model}'. "
                f"Supported models: {supported_models}"
            )

        return ChatNVIDIA(
            model=model,
            api_key=settings.NVIDIA_API_KEY,
            temperature=temperature,
            max_tokens=max_tokens,
            # Fail fast instead of the client's default 60s read timeout --
            # LLMService's cross-provider fallback is the faster recovery path.
            max_retries=0,
            timeout=15,
            **kwargs,
        )

    def list_models(self) -> list[str]:
        return self.SUPPORTED_MODELS.copy()

    def validate_credentials(self) -> bool:
        if not settings.NVIDIA_API_KEY:
            raise ConfigurationError(
                "NVIDIA_API_KEY is missing from the environment."
            )

        return True
