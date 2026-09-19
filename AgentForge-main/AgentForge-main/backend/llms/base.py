from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel


class BaseLLMProvider(ABC):
    provider_name: str

    @abstractmethod
    def create_chat_model(
        self,
        model: str,
        *,
        temperature: float = 0.1,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> BaseChatModel: ...

    @abstractmethod
    def list_models(
        self,
    ) -> list[str]: ...

    @abstractmethod
    def validate_credentials(
        self,
    ) -> bool: ...

    def supports_streaming(
        self,
    ) -> bool:
        return True

    def supports_structured_output(
        self,
    ) -> bool:
        return True

    def __repr__(
        self,
    ) -> str:
        return (
            f"{self.__class__.__name__}"
            f"(provider='{self.provider_name}')"
        )