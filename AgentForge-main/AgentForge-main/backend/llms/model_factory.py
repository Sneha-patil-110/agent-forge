from __future__ import annotations

from backend.llms.base import BaseLLMProvider
from backend.llms.providers.anthropic import AnthropicProvider
from backend.llms.providers.cerebras import CerebrasProvider
from backend.llms.providers.google import GoogleProvider
from backend.llms.providers.groq import GroqProvider
from backend.llms.providers.mistral import MistralProvider
from backend.llms.providers.openrouter import OpenRouterProvider
from backend.llms.providers.perplexity import PerplexityProvider
from backend.llms.providers.zai import ZaiProvider


class ModelFactory:
    _providers: dict[str, type[BaseLLMProvider]] = {
        "anthropic": AnthropicProvider,
        "cerebras": CerebrasProvider,
        "google": GoogleProvider,
        "groq": GroqProvider,
        "mistral": MistralProvider,
        "openrouter": OpenRouterProvider,
        "perplexity": PerplexityProvider,
        "zai": ZaiProvider,
    }

    @classmethod
    def create_provider(
        cls,
        provider_name: str,
    ) -> BaseLLMProvider:
        normalized_name = provider_name.strip().lower()

        provider_class = cls._providers.get(
            normalized_name
        )

        if provider_class is None:
            available_providers = ", ".join(
                sorted(cls._providers)
            )

            raise ValueError(
                f"Unknown provider '{provider_name}'. "
                f"Available providers: "
                f"{available_providers}"
            )

        return provider_class()