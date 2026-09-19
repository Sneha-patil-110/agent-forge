from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from backend.core.exceptions import MCPConfigurationError
from backend.mcp.config import MCPAuthType, MCPServerAuth, MCPServerConfig, MCPTransport, load_mcp_server_configs


def test_valid_stdio_config() -> None:
    config = MCPServerConfig(
        name="docs", enabled=True, transport=MCPTransport.STDIO, command="python", args=["-m", "x"]
    )
    assert config.command == "python"


def test_valid_http_config() -> None:
    config = MCPServerConfig(
        name="remote", enabled=True, transport=MCPTransport.HTTP, url="https://example.com/mcp"
    )
    assert config.url == "https://example.com/mcp"


def test_stdio_without_command_rejected() -> None:
    with pytest.raises(ValueError):
        MCPServerConfig(name="bad", enabled=True, transport=MCPTransport.STDIO)


def test_http_without_url_rejected() -> None:
    with pytest.raises(ValueError):
        MCPServerConfig(name="bad", enabled=True, transport=MCPTransport.HTTP)


def test_disabled_by_default() -> None:
    config = MCPServerConfig(name="x", transport=MCPTransport.STDIO, command="python")
    assert config.enabled is False


def test_unknown_field_rejected() -> None:
    with pytest.raises(ValueError):
        MCPServerConfig(
            name="x", transport=MCPTransport.STDIO, command="python", unexpected_field=True
        )


def test_env_stores_variable_names_not_values(monkeypatch) -> None:
    monkeypatch.setenv("AGENTFORGE_TEST_MCP_KEY", "the-real-secret")

    config = MCPServerConfig(
        name="x",
        enabled=True,
        transport=MCPTransport.STDIO,
        command="python",
        env={"API_KEY": "AGENTFORGE_TEST_MCP_KEY"},
    )

    assert config.env == {"API_KEY": "AGENTFORGE_TEST_MCP_KEY"}
    assert "the-real-secret" not in str(config.env)
    assert config.resolved_env() == {"API_KEY": "the-real-secret"}


def test_env_var_not_set_is_simply_omitted() -> None:
    config = MCPServerConfig(
        name="x",
        enabled=True,
        transport=MCPTransport.STDIO,
        command="python",
        env={"API_KEY": "THIS_ENV_VAR_DOES_NOT_EXIST_ANYWHERE"},
    )

    assert config.resolved_env() == {}


def test_load_missing_file_returns_empty_dict(tmp_path: Path) -> None:
    configs = load_mcp_server_configs(tmp_path / "does_not_exist.yaml")
    assert configs == {}


def test_load_empty_file_returns_empty_dict(tmp_path: Path) -> None:
    path = tmp_path / "mcp_servers.yaml"
    path.write_text("", encoding="utf-8")

    assert load_mcp_server_configs(path) == {}


def test_load_valid_file(tmp_path: Path) -> None:
    path = tmp_path / "mcp_servers.yaml"
    path.write_text(
        yaml.dump(
            {
                "docs": {
                    "enabled": True,
                    "transport": "stdio",
                    "command": "python",
                    "args": ["-m", "docs_server"],
                }
            }
        ),
        encoding="utf-8",
    )

    configs = load_mcp_server_configs(path)

    assert set(configs) == {"docs"}
    assert configs["docs"].enabled is True
    assert configs["docs"].command == "python"


def test_load_invalid_server_config_raises_mcp_configuration_error(tmp_path: Path) -> None:
    path = tmp_path / "mcp_servers.yaml"
    path.write_text(
        yaml.dump({"docs": {"enabled": True, "transport": "stdio"}}),
        encoding="utf-8",
    )

    with pytest.raises(MCPConfigurationError):
        load_mcp_server_configs(path)


def test_load_non_mapping_file_raises(tmp_path: Path) -> None:
    path = tmp_path / "mcp_servers.yaml"
    path.write_text(yaml.dump(["not", "a", "mapping"]), encoding="utf-8")

    with pytest.raises(MCPConfigurationError):
        load_mcp_server_configs(path)




def test_auth_defaults_to_none() -> None:
    config = MCPServerConfig(name="x", transport=MCPTransport.HTTP, url="https://example.com/mcp")
    assert config.auth.type == MCPAuthType.NONE
    assert config.resolved_auth_headers() == {}


def test_auth_type_without_credential_env_var_rejected() -> None:
    with pytest.raises(ValueError):
        MCPServerConfig(
            name="x",
            transport=MCPTransport.HTTP,
            url="https://example.com/mcp",
            auth=MCPServerAuth(type=MCPAuthType.BEARER),
        )


def test_auth_on_stdio_transport_rejected() -> None:
    with pytest.raises(ValueError):
        MCPServerConfig(
            name="x",
            transport=MCPTransport.STDIO,
            command="python",
            auth=MCPServerAuth(type=MCPAuthType.BEARER, credential_env_var="X"),
        )


def test_bearer_auth_resolves_to_authorization_header(monkeypatch) -> None:
    monkeypatch.setenv("AGENTFORGE_TEST_MCP_TOKEN", "secret-token")

    config = MCPServerConfig(
        name="x",
        transport=MCPTransport.HTTP,
        url="https://example.com/mcp",
        auth=MCPServerAuth(type=MCPAuthType.BEARER, credential_env_var="AGENTFORGE_TEST_MCP_TOKEN"),
    )

    assert config.resolved_auth_headers() == {"Authorization": "Bearer secret-token"}
    assert "secret-token" not in str(config.auth)


def test_api_key_auth_uses_custom_header_name(monkeypatch) -> None:
    monkeypatch.setenv("AGENTFORGE_TEST_MCP_KEY", "my-api-key")

    config = MCPServerConfig(
        name="x",
        transport=MCPTransport.HTTP,
        url="https://example.com/mcp",
        auth=MCPServerAuth(
            type=MCPAuthType.API_KEY, credential_env_var="AGENTFORGE_TEST_MCP_KEY", header_name="X-Custom-Key"
        ),
    )

    assert config.resolved_auth_headers() == {"X-Custom-Key": "my-api-key"}


def test_auth_with_unset_env_var_resolves_to_no_headers() -> None:
    config = MCPServerConfig(
        name="x",
        transport=MCPTransport.HTTP,
        url="https://example.com/mcp",
        auth=MCPServerAuth(type=MCPAuthType.BEARER, credential_env_var="THIS_ENV_VAR_DOES_NOT_EXIST_ANYWHERE"),
    )

    assert config.resolved_auth_headers() == {}
