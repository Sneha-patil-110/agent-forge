from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from backend.core.config import settings
from backend.core.exceptions import ConfigurationError
from backend.llms.base import BaseLLMProvider

class ZaiProvider(BaseLLMProvider):

    provider_name= "zai"

    SUPPORTED_MODELS = [
        "glm-5",
        "glm-5-air",
        "glm-5-flash",
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
        
        return ChatOpenAI(
            model= model,
            api_key= settings.ZAI_API_KEY,
            temperature= temperature,
            max_tokens= max_tokens,
            **kwargs
        )
    def list_models(self) -> list[str]:
        return self.SUPPORTED_MODELS.copy()

    def validate_credentials(self) -> bool:
        if not settings.ZAI_API_KEY:
            raise ConfigurationError(
                "ZAI_API_KEY is missing from the environment."
            )

        return True