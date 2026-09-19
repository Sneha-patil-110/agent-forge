from __future__ import annotations

import os
import sys
from enum import Enum
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.core.constants import MCP_CONNECTION_TIMEOUT, MCP_TOOL_CALL_TIMEOUT
from backend.core.exceptions import MCPConfigurationError
from backend.core.workspace import WORKSPACE_ROOT

CONFIG_PATH = Path(__file__).resolve().parent / "config" / "mcp_servers.yaml"

_PLACEHOLDERS = {
    "${WORKSPACE_ROOT}": str(WORKSPACE_ROOT),
    "${PYTHON}": sys.executable,
}


def _expand_placeholders(value: str) -> str:
    for placeholder, replacement in _PLACEHOLDERS.items():
        value = value.replace(placeholder, replacement)
    return value


def _normalize_stdio_command(command: str, args: list[str]) -> tuple[str, list[str]]:
    command = _expand_placeholders(command)
    args = [_expand_placeholders(arg) for arg in args]

    if os.name == "nt" and command == "npx":
        return "cmd", ["/c", "npx", *args]

    return command, args


class MCPTransport(str, Enum):
    STDIO = "stdio"
    HTTP = "http"


class MCPAuthType(str, Enum):
    NONE = "none"
    API_KEY = "api_key"
    BEARER = "bearer"
    CUSTOM_HEADER = "custom_header"
    OAUTH = "oauth"
    MTLS = "mtls"


class MCPServerAuth(BaseModel):

    model_config = ConfigDict(extra="forbid")

    type: MCPAuthType = MCPAuthType.NONE
    credential_env_var: str | None = Field(default=None)
    header_name: str | None = Field(default=None)

    @model_validator(mode="after")
    def _validate_credential_reference(self) -> MCPServerAuth:
        if self.type != MCPAuthType.NONE and not self.credential_env_var:
            if self.type not in (MCPAuthType.OAUTH, MCPAuthType.MTLS):
                raise ValueError(
                    f"auth.type '{self.type.value}' requires 'credential_env_var'."
                )

        return self


class MCPServerConfig(BaseModel):

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1)
    display_name: str | None = Field(default=None)
    description: str | None = Field(default=None)
    enabled: bool = False
    transport: MCPTransport

    command: str | None = Field(default=None)
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)

    url: str | None = Field(default=None)
    auth: MCPServerAuth = Field(default_factory=MCPServerAuth)

    connection_timeout: float = Field(default=MCP_CONNECTION_TIMEOUT, gt=0)
    tool_timeout: float = Field(default=MCP_TOOL_CALL_TIMEOUT, gt=0)

    capabilities: dict[str, list[str]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_transport_fields(self) -> MCPServerConfig:
        if self.transport == MCPTransport.STDIO and not self.command:
            raise ValueError(
                f"MCP server '{self.name}': transport 'stdio' requires 'command'."
            )

        if self.transport == MCPTransport.HTTP and not self.url:
            raise ValueError(
                f"MCP server '{self.name}': transport 'http' requires 'url'."
            )

        if self.transport == MCPTransport.STDIO and self.auth.type != MCPAuthType.NONE:
            raise ValueError(
                f"MCP server '{self.name}': auth is only meaningful for transport 'http'."
            )

        return self

    def resolved_env(self) -> dict[str, str]:
        resolved: dict[str, str] = {}

        for key, env_var_name in self.env.items():
            value = os.environ.get(env_var_name)

            if value is not None:
                resolved[key] = value

        return resolved

    def resolved_auth_headers(self) -> dict[str, str]:

        if self.auth.type == MCPAuthType.NONE or not self.auth.credential_env_var:
            return {}

        value = os.environ.get(self.auth.credential_env_var)

        if value is None:
            return {}

        if self.auth.type == MCPAuthType.API_KEY:
            return {self.auth.header_name or "X-API-Key": value}

        if self.auth.type == MCPAuthType.BEARER:
            return {"Authorization": f"Bearer {value}"}

        if self.auth.type == MCPAuthType.CUSTOM_HEADER:
            return {self.auth.header_name or "Authorization": value}

        return {}


def load_mcp_server_configs(config_path: Path = CONFIG_PATH) -> dict[str, MCPServerConfig]:

    if not config_path.exists():
        return {}

    with config_path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file)

    if raw is None:
        return {}

    if not isinstance(raw, dict):
        raise MCPConfigurationError(
            "mcp_servers.yaml must contain a mapping of server name to configuration."
        )

    configs: dict[str, MCPServerConfig] = {}

    for server_name, server_config in raw.items():
        if not isinstance(server_config, dict):
            raise MCPConfigurationError(
                f"MCP server '{server_name}' configuration must be a mapping."
            )

        if server_config.get("transport") == "stdio" and server_config.get("command"):
            command, args = _normalize_stdio_command(
                server_config["command"], server_config.get("args", [])
            )
            server_config = {**server_config, "command": command, "args": args}

        try:
            configs[server_name] = MCPServerConfig(name=server_name, **server_config)
        except ValueError as error:
            raise MCPConfigurationError(
                f"Invalid configuration for MCP server '{server_name}': {error}",
                details={"server": server_name},
            ) from error

    return configs


def build_capability_map(configs: dict[str, MCPServerConfig]) -> dict[str, str]:

    mapping: dict[str, str] = {}

    for server_name, config in configs.items():
        for capability, tool_names in config.capabilities.items():
            for tool_name in tool_names:
                mapping[f"{server_name}.{tool_name}"] = capability

    return mapping
