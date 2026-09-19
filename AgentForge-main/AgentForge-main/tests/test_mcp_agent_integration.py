
from __future__ import annotations

import asyncio
import json
import sys

from langchain_core.messages import AIMessage

from backend.agents.documenter_agent import DocumentationAgent
from backend.core.constants import MAX_MCP_TOOL_ROUNDS
from backend.mcp.client_manager import MCPClientManager
from backend.mcp.config import MCPServerConfig, MCPTransport
from backend.mcp.discovery import discover_tools
from backend.mcp.executor import MCPToolExecutor, set_current_run_id
from backend.mcp.permissions import MCPPermissionPolicy
from backend.mcp.registry import MCPToolRegistry
from backend.state.execution_state import AgentType, WorkflowStatus
from backend.state.workflow_state import WorkflowState

RUN_ID = "af_20260715_deadbeef"

DOC_JSON = json.dumps(
    {
        "generated_docs": [
            {"title": "README", "path": "README.md", "content": "# Test", "description": None}
        ],
        "documentation_summary": "done",
        "pending_documentation": [],
    }
)


class _StubPromptService:
    def load(self, prompt_file: str) -> str:
        return "system prompt"


def _real_stack():
    config = MCPServerConfig(
        name="test",
        enabled=True,
        transport=MCPTransport.STDIO,
        command=sys.executable,
        args=["-m", "tests.support.mcp_test_server"],
    )
    manager = MCPClientManager({"test": config})
    registry = MCPToolRegistry()
    tools = asyncio.run(discover_tools(manager, "test"))
    registry.register_server_tools("test", tools)

    return manager, registry


def test_agent_uses_real_mcp_tool_then_produces_structured_output():
    manager, registry = _real_stack()

    policy = MCPPermissionPolicy({AgentType.DOCUMENTATION: frozenset({"test.get_test_document"})})
    executor = MCPToolExecutor(client_manager=manager, registry=registry, permission_policy=policy)
    set_current_run_id(RUN_ID)

    class _ScriptedLLM:
        def __init__(self):
            self.calls = 0

        def invoke(self, *, model_role, prompt, context, response_schema=None, tools=None, tool_choice=None, extra_messages=None):
            self.calls += 1
            if self.calls == 1:
                assert tools is not None
                return AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "test__get_test_document", "args": {"topic": "AgentForge"}, "id": "call_1"}
                    ],
                )
            return AIMessage(content=DOC_JSON)

    llm = _ScriptedLLM()
    agent = DocumentationAgent(
        _StubPromptService(),
        llm,
        mcp_executor=executor,
        mcp_registry=registry,
        mcp_tool_identities=["test.get_test_document"],
    )

    result_state = agent.run(WorkflowState())

    assert llm.calls == 2
    assert result_state.documentation.documentation_summary == "done"
    assert result_state.execution.workflow_status == WorkflowStatus.COMPLETED

    asyncio.run(manager.close_all())


def test_agent_without_mcp_tools_behaves_exactly_as_before():
    class _PlainLLM:
        def __init__(self):
            self.calls = 0

        def invoke(self, *, model_role, prompt, context, response_schema=None, tools=None, tool_choice=None, extra_messages=None):
            self.calls += 1
            assert tools is None
            assert extra_messages is None
            return AIMessage(content=DOC_JSON)

    llm = _PlainLLM()
    agent = DocumentationAgent(_StubPromptService(), llm)

    result_state = agent.run(WorkflowState())

    assert llm.calls == 1
    assert result_state.execution.workflow_status == WorkflowStatus.COMPLETED


def test_bounded_loop_forces_final_answer_after_max_rounds():
    manager, registry = _real_stack()

    policy = MCPPermissionPolicy({AgentType.DOCUMENTATION: frozenset({"test.*"})})
    executor = MCPToolExecutor(client_manager=manager, registry=registry, permission_policy=policy)
    set_current_run_id(RUN_ID)

    class _StubbornLLM:
        def __init__(self):
            self.calls = 0

        def invoke(self, *, model_role, prompt, context, response_schema=None, tools=None, tool_choice=None, extra_messages=None):
            self.calls += 1
            if tools and tool_choice != "none":
                return AIMessage(
                    content="",
                    tool_calls=[{"name": "test__echo", "args": {"message": "again"}, "id": f"call_{self.calls}"}],
                )
            return AIMessage(content=DOC_JSON)

    llm = _StubbornLLM()
    agent = DocumentationAgent(
        _StubPromptService(),
        llm,
        mcp_executor=executor,
        mcp_registry=registry,
        mcp_tool_identities=["test.echo"],
    )

    result_state = agent.run(WorkflowState())


    assert llm.calls == MAX_MCP_TOOL_ROUNDS + 1
    assert result_state.execution.workflow_status == WorkflowStatus.COMPLETED

    asyncio.run(manager.close_all())


def test_unauthorized_tool_call_from_llm_does_not_crash_agent():

    manager, registry = _real_stack()

    policy = MCPPermissionPolicy({AgentType.DOCUMENTATION: frozenset({"test.echo"})})
    executor = MCPToolExecutor(client_manager=manager, registry=registry, permission_policy=policy)
    set_current_run_id(RUN_ID)

    class _MisbehavingLLM:
        def __init__(self):
            self.calls = 0

        def invoke(self, *, model_role, prompt, context, response_schema=None, tools=None, tool_choice=None, extra_messages=None):
            self.calls += 1
            if self.calls == 1:
                return AIMessage(
                    content="",
                    tool_calls=[{"name": "test__add", "args": {"a": 1, "b": 2}, "id": "call_1"}],
                )
            return AIMessage(content=DOC_JSON)

    llm = _MisbehavingLLM()
    agent = DocumentationAgent(
        _StubPromptService(),
        llm,
        mcp_executor=executor,
        mcp_registry=registry,
        mcp_tool_identities=["test.echo"],
    )

    result_state = agent.run(WorkflowState())

    assert result_state.execution.workflow_status == WorkflowStatus.COMPLETED

    asyncio.run(manager.close_all())
