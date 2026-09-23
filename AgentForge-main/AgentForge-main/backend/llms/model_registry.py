from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import yaml
from langchain_core.language_models.chat_models import BaseChatModel

from backend.llms.model_factory import ModelFactory


class ModelRegistry:
    _config: ClassVar[dict[str, dict[str, Any]] | None] = None

    def __init__(self) -> None:
        if ModelRegistry._config is None:
            ModelRegistry._config = self._load_config()

        self.config = ModelRegistry._config

    def _load_config(
        self,
    ) -> dict[str, dict[str, Any]]:
        config_path = (
            Path(__file__).resolve().parent
            / "config"
            / "models.yaml"
        )

        if not config_path.exists():
            raise FileNotFoundError(
                f"Model configuration file was not found: "
                f"{config_path}"
            )

        with config_path.open(
            "r",
            encoding="utf-8",
        ) as file:
            config = yaml.safe_load(file)

        if not isinstance(config, dict):
            raise ValueError(
                "models.yaml must contain a mapping "
                "of agent roles to model configurations."
            )

        return config

    def get_model(
        self,
        role: str,
    ) -> BaseChatModel:
        return self.build_model(self._require_role_config(role), role=role)

    def get_fallback_configs(self, role: str) -> list[dict[str, Any]]:
        """Additional {provider, model, ...} configs to try, in order, if the
        role's primary model invocation fails."""
        model_config = self._require_role_config(role)

        return list(model_config.get("fallbacks") or [])

    def build_model(self, model_config: dict[str, Any], *, role: str) -> BaseChatModel:
        provider_name = model_config.get("provider")
        model_name = model_config.get("model")

        if not provider_name:
            raise ValueError(f"Provider is missing for role '{role}'.")

        if not model_name:
            raise ValueError(f"Model is missing for role '{role}'.")

        provider = ModelFactory.create_provider(provider_name)

        model_kwargs = {
            key: value
            for key, value in model_config.items()
            if key not in {"provider", "model", "fallbacks"}
        }

        return provider.create_chat_model(
            model=model_name,
            **model_kwargs,
        )

    def _require_role_config(self, role: str) -> dict[str, Any]:
        model_config = self.config.get(role)

        if model_config is None:
            available_roles = ", ".join(self.config.keys())

            raise ValueError(
                f"No model configuration found for role "
                f"'{role}'. Available roles: "
                f"{available_roles}"
            )

        return model_config