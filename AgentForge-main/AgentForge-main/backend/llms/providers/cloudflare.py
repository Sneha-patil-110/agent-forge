from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from backend.core.config import settings
from backend.core.exceptions import ConfigurationError
from backend.llms.base import BaseLLMProvider


class CloudflareProvider(BaseLLMProvider):
    provider_name = "cloudflare"

    SUPPORTED_MODELS: list[str] = [
        "@cf/meta/llama-3.1-8b-instruct-fp8",
        "@cf/qwen/qwen2.5-coder-32b-instruct",
        "@cf/qwen/qwen3.8-27b",
        "@cf/openai/gpt-oss-120b",
        "@cf/openai/gpt-oss-20b",
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
                f"Unsupported Cloudflare model '{model}'. "
                f"Supported models: {supported_models}"
            )

        return ChatOpenAI(
            model=model,
            api_key=settings.CLOUDFLARE_API_TOKEN,
            base_url=(
                "https://api.cloudflare.com/client/v4/accounts/"
                f"{settings.CLOUDFLARE_ACCOUNT_ID}/ai/v1"
            ),
            temperature=temperature,
            max_tokens=max_tokens,
            max_retries=0,
            timeout=20,
            **kwargs,
        )

    def list_models(self) -> list[str]:
        return self.SUPPORTED_MODELS.copy()

    def validate_credentials(self) -> bool:
        if not settings.CLOUDFLARE_API_TOKEN:
            raise ConfigurationError(
                "CLOUDFLARE_API_TOKEN is missing from the environment."
            )

        if not settings.CLOUDFLARE_ACCOUNT_ID:
            raise ConfigurationError(
                "CLOUDFLARE_ACCOUNT_ID is missing from the environment."
            )

        return True
