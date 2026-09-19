from __future__ import annotations

from backend.state.execution_state import AgentType


class MCPPermissionPolicy:

    def __init__(
        self,
        allowed: dict[AgentType, frozenset[str]] | None = None,
        capability_map: dict[str, str] | None = None,
    ) -> None:
        self._allowed: dict[AgentType, frozenset[str]] = dict(allowed or {})
        self._capability_map: dict[str, str] = dict(capability_map or {})

    def is_authorized(self, agent: AgentType, tool_identity: str) -> bool:
        allowed = self._allowed.get(agent, frozenset())

        if tool_identity in allowed:
            return True

        server_name = tool_identity.split(".", 1)[0]

        if f"{server_name}.*" in allowed:
            return True

        capability = self._capability_map.get(tool_identity)

        return capability is not None and f"{server_name}:{capability}" in allowed

    def allowed_identities(self, agent: AgentType, registry) -> list[str]:
        return [
            tool.identity
            for tool in registry.all_tools()
            if self.is_authorized(agent, tool.identity)
        ]
