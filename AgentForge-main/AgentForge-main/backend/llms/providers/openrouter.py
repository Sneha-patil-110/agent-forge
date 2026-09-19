from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openrouter import ChatOpenRouter

from backend.core.config import settings
from backend.core.exceptions import ConfigurationError
from backend.llms.base import BaseLLMProvider

class OpenRouterProvider(BaseLLMProvider):

    provider_name= "openrouter"

    SUPPORTED_MODELS = [
        "anthropic/claude-opus-4.5",
        "anthropic/claude-sonnet-4.5",
        "openai/gpt-5.5",
        "deepseek/deepseek-r1",
        "qwen/qwen3-coder",
    ]

    def __init__(self)->None:
        self.validate_credentials()
    
    def create_chat_model(
            self,
            model: str,
            *,
            temperature: float=0.2,
            max_tokens: int | None= None,
            **kwargs: Any,
    )-> BaseChatModel:
        if model not in self.SUPPORTED_MODELS:
            raise ValueError(
                f"Unsupported model '{model}'. "
                f"Supported models: {self.SUPPORTED_MODELS}"
            )
        
        return ChatOpenRouter(
            model= model,
            api_key= settings.OPENROUTER_API_KEY,
            temperature= temperature,
            max_tokens= max_tokens,
            **kwargs
        )
    def list_models(self) -> list[str]:
        return self.SUPPORTED_MODELS.copy()

    def validate_credentials(self) -> bool:
        if not settings.OPENROUTER_API_KEY:
            raise ConfigurationError(
                "OPENROUTER_API_KEY is missing from the environment."
            )

        return True