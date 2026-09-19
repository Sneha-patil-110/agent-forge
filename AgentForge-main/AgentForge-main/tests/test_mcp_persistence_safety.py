
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from langchain_core.messages import AIMessage

from backend.agents.analysis_agent import AnalysisAgent
from backend.agents.architect_agent import ArchitectAgent
from backend.agents.debugger_agent import DebuggerAgent
from backend.agents.developer_agent import DeveloperAgent
from backend.agents.documenter_agent import DocumentationAgent
from backend.agents.planner_agent import PlannerAgent
from backend.agents.reviewer_agent import ReviewerAgent
from backend.agents.tester_agent import TesterAgent
from backend.events.dispatcher import EventDispatcher
from backend.graph.builder import WorkflowBuilder
from backend.graph.nodes import WorkflowNodes
from backend.graph.workflow import WorkflowNode
from backend.mcp.client_manager import MCPClientManager
from backend.mcp.config import MCPServerConfig, MCPTransport
from backend.mcp.discovery import discover_tools
from backend.mcp.executor import MCPToolExecutor, set_current_run_id
from backend.mcp.permissions import MCPPermissionPolicy
from backend.mcp.registry import MCPToolRegistry
from backend.services.checkpoint_service import CheckpointService
from backend.services.materialization_service import MaterializationService
from backend.services.testing_service import TestingService
from backend.state.execution_state import AgentType, WorkflowStatus
from backend.state.workflow_state import WorkflowState
from backend.tools.filesystem_tool import FilesystemTool
from backend.tools.terminal_tool import TerminalTool
from backend.tools.tool_registry import ToolRegistry
from backend.utils.run_id import generate_run_id

from tests.test_review_retry_integration import (
    REVIEW_PASSED,
    TEST_PLAN,
    VALID_ARCHITECTURE_STATE,
    VALID_PLANNING_STATE,
    VALID_PROJECT_STATE,
    WORKING_CALC_CONTENT,
    StubPromptService,
    _calc_file,
    _implementation_payload,
    _initial_state,
    _test_file,
)


def test_workflow_state_schema_has_no_mcp_runtime_fields() -> None:
    forbidden_substrings = ("mcp_client", "mcp_executor", "mcp_registry", "fastmcp")

    for field_name in WorkflowState.model_fields:
        assert not any(s in field_name.lower() for s in forbidden_substrings)

    for sub_model_field in WorkflowState.model_fields.values():
        annotation = sub_model_field.annotation
        model_fields = getattr(annotation, "model_fields", None)
        if model_fields:
            for name in model_fields:
                assert not any(s in name.lower() for s in forbidden_substrings)


def _real_mcp_stack(run_id: str):
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

    policy = MCPPermissionPolicy({AgentType.DOCUMENTATION: frozenset({"test.*"})})
    executor = MCPToolExecutor(client_manager=manager, registry=registry, permission_policy=policy)
    set_current_run_id(run_id)

    return manager, registry, executor


class _DocumentationScriptedLLM:

    DOC_JSON = json.dumps(
        {
            "generated_docs": [
                {"title": "README", "path": "README.md", "content": "# T", "description": None}
            ],
            "documentation_summary": "done",
            "pending_documentation": [],
        }
    )

    def __init__(self) -> None:
        self.documentation_calls = 0

    def invoke(self, *, model_role, prompt, context, response_schema=None, tools=None, extra_messages=None):
        if model_role == "analysis":
            return AIMessage(content=json.dumps(VALID_PROJECT_STATE))
        if model_role == "planner":
            return AIMessage(content=json.dumps(VALID_PLANNING_STATE))
        if model_role == "architect":
            return AIMessage(content=json.dumps(VALID_ARCHITECTURE_STATE))
        if model_role == "developer":
            return AIMessage(
                content=json.dumps(
                    _implementation_payload(
                        _calc_file(WORKING_CALC_CONTENT, "Calculator module."), _test_file()
                    )
                )
            )
        if model_role == "tester":
            return AIMessage(content=json.dumps(TEST_PLAN))
        if model_role == "reviewer":
            return AIMessage(content=json.dumps(REVIEW_PASSED))
        if model_role == "documentation":
            self.documentation_calls += 1
            if self.documentation_calls == 1:
                return AIMessage(
                    content="",
                    tool_calls=[{"name": "test.echo", "args": {"message": "doc"}, "id": "c1"}],
                )
            return AIMessage(content=self.DOC_JSON)
        raise AssertionError(f"unexpected role {model_role}")


def _build_nodes(output_directory: Path, llm_service, mcp_executor, mcp_registry) -> WorkflowNodes:
    prompt_service = StubPromptService()

    tool_registry = ToolRegistry()
    tool_registry.register(FilesystemTool(workspace=output_directory))
    tool_registry.register(TerminalTool(workspace=output_directory))

    return WorkflowNodes(
        analysis_agent=AnalysisAgent(prompt_service, llm_service),
        planner_agent=PlannerAgent(prompt_service, llm_service),
        architect_agent=ArchitectAgent(prompt_service, llm_service),
        developer_agent=DeveloperAgent(prompt_service, llm_service),
        tester_agent=TesterAgent(prompt_service, llm_service),
        debugger_agent=DebuggerAgent(prompt_service, llm_service),
        reviewer_agent=ReviewerAgent(prompt_service, llm_service),
        documentation_agent=DocumentationAgent(
            prompt_service,
            llm_service,
            mcp_executor=mcp_executor,
            mcp_registry=mcp_registry,
            mcp_tool_identities=["test.echo"],
        ),
        materialization_service=MaterializationService(tool_registry),
        testing_service=TestingService(tool_registry),
    )


def test_resume_after_mcp_tool_use_recreates_infrastructure_and_state_serializes_cleanly(
    tmp_path: Path,
) -> None:
    run_id = generate_run_id()
    output_directory = tmp_path / "project"
    output_directory.mkdir()

    checkpoint_service = CheckpointService(runs_root=tmp_path / "runs")
    config = {"configurable": {"thread_id": run_id}}

    llm_a = _DocumentationScriptedLLM()
    manager_a, registry_a, executor_a = _real_mcp_stack(run_id)
    dispatcher_a = EventDispatcher()

    checkpointer_a = checkpoint_service.checkpointer_for_run(run_id)
    graph_a = WorkflowBuilder(_build_nodes(output_directory, llm_a, executor_a, registry_a)).build(
        checkpointer=checkpointer_a,
        event_dispatcher=dispatcher_a,
        run_id=run_id,
        interrupt_after=[WorkflowNode.ARCHITECT.value],
    )

    graph_a.invoke(_initial_state(output_directory), config=config)
    asyncio.run(manager_a.close_all())

    llm_b = _DocumentationScriptedLLM()
    manager_b, registry_b, executor_b = _real_mcp_stack(run_id)

    checkpointer_b = checkpoint_service.checkpointer_for_run(run_id)
    graph_b = WorkflowBuilder(_build_nodes(output_directory, llm_b, executor_b, registry_b)).build(
        checkpointer=checkpointer_b,
        run_id=run_id,
    )

    result = graph_b.invoke(None, config=config)
    final_state = WorkflowState.model_validate(result)

    assert final_state.execution.workflow_status == WorkflowStatus.COMPLETED
    assert final_state.documentation.documentation_summary == "done"
    assert final_state.execution.test_retry_count == 0
    assert final_state.execution.review_retry_count == 0
    assert llm_b.documentation_calls == 2

    round_tripped = WorkflowState.model_validate_json(final_state.model_dump_json())
    assert round_tripped == final_state

    asyncio.run(manager_b.close_all())
