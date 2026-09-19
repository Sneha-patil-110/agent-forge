
from __future__ import annotations

from pathlib import Path

from backend.events.dispatcher import EventDispatcher
from backend.events.event_types import WorkflowEvent
from backend.graph.builder import WorkflowBuilder
from backend.graph.nodes import WorkflowNodes
from backend.services.materialization_service import MaterializationService
from backend.services.testing_service import TestingService
from backend.tools.filesystem_tool import FilesystemTool
from backend.tools.terminal_tool import TerminalTool
from backend.tools.tool_registry import ToolRegistry

from tests.test_review_retry_integration import (
    DEBUG_ANALYSIS,
    REVIEW_PASSED,
    TEST_PLAN,
    VALID_ARCHITECTURE_STATE,
    VALID_DOCUMENTATION_STATE,
    VALID_PLANNING_STATE,
    VALID_PROJECT_STATE,
    ScriptedLLMService,
    StubPromptService,
    _as_workflow_state,
    _implementation_payload,
    _initial_state,
)

SECRET_MARKER = "gsk_super_secret_value_should_never_appear"
PROMPT_TEXT = "SYSTEM PROMPT WITH FULL INSTRUCTIONS " * 5


def test_events_never_contain_secrets_prompts_or_generated_code(tmp_path: Path) -> None:
    output_directory = tmp_path / "project"
    output_directory.mkdir()

    secret_file_content = f"API_KEY = '{SECRET_MARKER}'\n" * 3

    llm_service = ScriptedLLMService(
        {
            "analysis": [VALID_PROJECT_STATE],
            "planner": [VALID_PLANNING_STATE],
            "architect": [VALID_ARCHITECTURE_STATE],
            "developer": [
                _implementation_payload(
                    {
                        "path": "app.py",
                        "content": secret_file_content,
                        "language": "python",
                        "description": "d",
                    }
                )
            ],
            "tester": [TEST_PLAN],
            "debugger": [DEBUG_ANALYSIS],
            "reviewer": [REVIEW_PASSED],
            "documentation": [VALID_DOCUMENTATION_STATE],
        }
    )

    class _LoudPromptService(StubPromptService):
        def load(self, prompt_file: str) -> str:
            return PROMPT_TEXT

    prompt_service = _LoudPromptService()

    from backend.agents.analysis_agent import AnalysisAgent
    from backend.agents.architect_agent import ArchitectAgent
    from backend.agents.debugger_agent import DebuggerAgent
    from backend.agents.developer_agent import DeveloperAgent
    from backend.agents.documenter_agent import DocumentationAgent
    from backend.agents.planner_agent import PlannerAgent
    from backend.agents.reviewer_agent import ReviewerAgent
    from backend.agents.tester_agent import TesterAgent

    tool_registry = ToolRegistry()
    tool_registry.register(FilesystemTool(workspace=output_directory))
    tool_registry.register(TerminalTool(workspace=output_directory))

    nodes = WorkflowNodes(
        analysis_agent=AnalysisAgent(prompt_service, llm_service),
        planner_agent=PlannerAgent(prompt_service, llm_service),
        architect_agent=ArchitectAgent(prompt_service, llm_service),
        developer_agent=DeveloperAgent(prompt_service, llm_service),
        tester_agent=TesterAgent(prompt_service, llm_service),
        debugger_agent=DebuggerAgent(prompt_service, llm_service),
        reviewer_agent=ReviewerAgent(prompt_service, llm_service),
        documentation_agent=DocumentationAgent(prompt_service, llm_service),
        materialization_service=MaterializationService(tool_registry),
        testing_service=TestingService(tool_registry),
    )

    dispatcher = EventDispatcher()
    events: list[WorkflowEvent] = []
    dispatcher.subscribe(events.append)

    graph = WorkflowBuilder(nodes).build(
        event_dispatcher=dispatcher, run_id="af_20260714_deadbeef"
    )

    result = _as_workflow_state(graph.invoke(_initial_state(output_directory)))

    assert len(events) > 0
    assert result.implementation.generated_code[0].content == secret_file_content

    serialized_events = "\n".join(event.model_dump_json() for event in events)

    assert SECRET_MARKER not in serialized_events
    assert PROMPT_TEXT not in serialized_events
    assert secret_file_content not in serialized_events
    assert "API_KEY" not in serialized_events
