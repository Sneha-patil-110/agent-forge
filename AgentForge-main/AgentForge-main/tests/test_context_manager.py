from __future__ import annotations

import pytest

from langchain_core.messages import AIMessage, HumanMessage

from backend.mcp.discovery import DiscoveredTool
from backend.mcp.registry import MCPToolRegistry
from backend.services.context_manager import ContextManager, ContextSection, Priority
from backend.state.debug_state import DebugState, SuggestedChange
from backend.state.execution_state import RepairTrigger
from backend.state.implementation_state import GeneratedCode
from backend.state.review_state import ReviewIssue, Severity
from backend.state.workflow_state import WorkflowState

ALL_AGENTS = [
    "analysis",
    "planner",
    "architect",
    "developer",
    "tester",
    "reviewer",
    "documentation",
    "debugger",
]


def _state_with_generated_files(*paths: str) -> WorkflowState:
    state = WorkflowState()
    state.implementation.generated_code = [
        GeneratedCode(path=path, content=f"# content of {path}\n", language="python")
        for path in paths
    ]
    return state




@pytest.mark.parametrize("agent_name", ALL_AGENTS)
def test_build_context_succeeds_for_every_agent_on_default_state(agent_name: str) -> None:
    manager = ContextManager()

    text = manager.build_context(agent_name=agent_name, state=WorkflowState())

    assert isinstance(text, str)
    assert text.strip() != ""


def test_followup_request_section_added_for_non_analysis_agents_on_continuation() -> None:
    manager = ContextManager()
    state = WorkflowState()
    state.conversation.messages = [
        HumanMessage(content="Build a fastapi expense tracker"),
        AIMessage(content="Updated 3 files. Tests passed."),
        HumanMessage(content="Add authentication"),
    ]

    text = manager.build_context(agent_name="planner", state=state)

    assert "Latest Follow-up Request" in text
    assert "Add authentication" in text
    assert "Build a fastapi expense tracker" not in text


def test_followup_request_section_absent_on_a_first_message() -> None:
    manager = ContextManager()
    state = WorkflowState()
    state.conversation.messages = [HumanMessage(content="Build a fastapi expense tracker")]

    text = manager.build_context(agent_name="planner", state=state)

    assert "Latest Follow-up Request" not in text


def test_followup_request_section_absent_for_analysis_itself() -> None:
    manager = ContextManager()
    state = WorkflowState()
    state.conversation.messages = [
        HumanMessage(content="Build a fastapi expense tracker"),
        AIMessage(content="Updated 3 files. Tests passed."),
        HumanMessage(content="Add authentication"),
    ]

    text = manager.build_context(agent_name="analysis", state=state)

    assert "Latest Follow-up Request" not in text


def test_unknown_agent_name_raises() -> None:
    manager = ContextManager()

    with pytest.raises(ValueError):
        manager.build_context(agent_name="not-a-real-agent", state=WorkflowState())


def test_analysis_context_includes_conversation_and_project_sections() -> None:
    manager = ContextManager()
    state = WorkflowState()
    state.conversation.summary = "User wants a task manager."

    text = manager.build_context(agent_name="analysis", state=state)

    assert "Conversation History" in text
    assert "Conversation Summary" in text
    assert "Current Project State" in text
    assert "User wants a task manager." in text
    assert "Planning Information" not in text
    assert "Architecture Information" not in text


def test_planner_context_includes_project_and_planning_but_not_architecture() -> None:
    manager = ContextManager()

    text = manager.build_context(agent_name="planner", state=WorkflowState())

    assert "Project Information" in text
    assert "Existing Planning Information" in text
    assert "Architecture Information" not in text


def test_reviewer_context_includes_implementation_and_review_sections() -> None:
    manager = ContextManager()

    text = manager.build_context(agent_name="reviewer", state=WorkflowState())

    assert "Implementation Information" in text
    assert "Existing Review Information" in text


def test_tester_context_includes_implementation_and_testing_sections() -> None:
    manager = ContextManager()

    text = manager.build_context(agent_name="tester", state=WorkflowState())

    assert "Implementation Information" in text
    assert "Test Execution Evidence" in text


def test_documentation_context_includes_implementation_and_review_sections() -> None:
    manager = ContextManager()

    text = manager.build_context(agent_name="documentation", state=WorkflowState())

    assert "Implementation Information" in text
    assert "Review Information" in text


def test_debugger_context_includes_test_evidence_and_omits_previous_analysis_when_absent() -> None:
    manager = ContextManager()

    text = manager.build_context(agent_name="debugger", state=WorkflowState())

    assert "Real Test Execution Evidence" in text
    assert "Previous Debug Analysis" not in text


def test_debugger_context_includes_previous_analysis_when_present() -> None:
    manager = ContextManager()
    state = WorkflowState()
    state.debug.failure_summary = "test_divide_by_zero failed."
    state.debug.root_cause = "divide() does not validate the divisor."

    text = manager.build_context(agent_name="debugger", state=state)

    assert "Previous Debug Analysis" in text
    assert "divide() does not validate the divisor." in text




def test_developer_context_omits_all_feedback_on_initial_run() -> None:
    manager = ContextManager()

    text = manager.build_context(agent_name="developer", state=WorkflowState())

    assert "Review Feedback" not in text
    assert "Debug Feedback" not in text


def test_developer_context_includes_debug_and_review_feedback_on_review_retry() -> None:
    manager = ContextManager()
    state = WorkflowState()
    state.execution.last_repair_trigger = RepairTrigger.REVIEW_FEEDBACK
    state.review.review_summary = "Missing input validation."
    state.review.issues = [
        ReviewIssue(
            title="No validation",
            description="Endpoint accepts unvalidated input.",
            severity=Severity.HIGH,
            file_path="app.py",
        )
    ]
    state.debug.root_cause = "The endpoint does not validate the request body."
    state.debug.affected_files = ["app.py"]

    text = manager.build_context(agent_name="developer", state=state)

    assert "Review Feedback Evidence" in text
    assert "Missing input validation." in text
    assert "No validation" in text
    assert "Debug Feedback" in text
    assert "The endpoint does not validate the request body." in text


def test_developer_context_includes_only_debug_feedback_on_test_retry() -> None:
    manager = ContextManager()
    state = WorkflowState()
    state.execution.last_repair_trigger = RepairTrigger.TEST_FAILURE
    state.debug.root_cause = "divide() does not validate the divisor."
    state.testing.stderr = "ZeroDivisionError: division by zero"

    text = manager.build_context(agent_name="developer", state=state)

    assert "Debug Feedback" in text
    assert "Failed Test Execution Evidence" in text
    assert "divide() does not validate the divisor." in text
    assert "ZeroDivisionError" in text
    assert "Review Feedback" not in text




def test_developer_repair_filters_generated_code_to_affected_files() -> None:
    manager = ContextManager()
    state = _state_with_generated_files("calc.py", "unrelated.py", "also_unrelated.py")
    state.execution.last_repair_trigger = RepairTrigger.TEST_FAILURE
    state.debug.affected_files = ["calc.py"]

    text = manager.build_context(agent_name="developer", state=state)

    assert "calc.py" in text
    assert "unrelated.py" not in text
    assert "also_unrelated.py" not in text
    assert manager.last_metadata.selected_file_count == 1


def test_developer_repair_also_includes_files_from_suggested_changes() -> None:
    manager = ContextManager()
    state = _state_with_generated_files("calc.py", "utils.py", "unrelated.py")
    state.execution.last_repair_trigger = RepairTrigger.TEST_FAILURE
    state.debug.affected_files = ["calc.py"]
    state.debug.suggested_changes = [
        SuggestedChange(file_path="utils.py", description="Add a helper.")
    ]

    text = manager.build_context(agent_name="developer", state=state)

    assert "calc.py" in text
    assert "utils.py" in text
    assert "unrelated.py" not in text


def test_developer_review_repair_filters_generated_code_to_debug_affected_files() -> None:
    manager = ContextManager()
    state = _state_with_generated_files("app.py", "unrelated.py")
    state.execution.last_repair_trigger = RepairTrigger.REVIEW_FEEDBACK
    state.review.issues = [
        ReviewIssue(
            title="No validation",
            description="Endpoint accepts unvalidated input.",
            severity=Severity.HIGH,
            file_path="app.py",
        )
    ]
    state.debug.affected_files = ["app.py"]

    text = manager.build_context(agent_name="developer", state=state)

    assert '"app.py"' in text
    assert "unrelated.py" not in text


def test_file_selection_falls_back_to_all_files_when_relevant_paths_do_not_match() -> None:
    manager = ContextManager()
    state = _state_with_generated_files("calc.py")
    state.execution.last_repair_trigger = RepairTrigger.TEST_FAILURE
    state.debug.affected_files = ["some/other/path.py"]

    text = manager.build_context(agent_name="developer", state=state)

    assert "calc.py" in text
    assert manager.last_metadata.selected_file_count == 1


def test_non_repair_agents_receive_all_generated_files_unfiltered() -> None:
    manager = ContextManager()
    state = _state_with_generated_files("a.py", "b.py", "c.py")

    manager.build_context(agent_name="reviewer", state=state)

    assert manager.last_metadata.selected_file_count == 3




def test_low_priority_sections_are_dropped_before_high_priority_ones() -> None:
    manager = ContextManager(token_budget=10_000_000)

    sections = [
        ContextSection("Keep Me (critical)", "critical content", Priority.CRITICAL, required=True),
        ContextSection("Drop Me First (low)", "low priority content " * 500, Priority.LOW),
        ContextSection("Keep Me Too (high)", "high priority content", Priority.HIGH),
    ]

    manager.token_budget = 20
    text, metadata = manager._assemble(
        "test-agent", sections, selected_file_count=0, documentation_section_count=0
    )

    assert "Drop Me First (low)" not in text
    assert "Keep Me (critical)" in metadata.dropped_sections or "Keep Me (critical)" in text
    assert metadata.dropped_sections == ["Drop Me First (low)"]


def test_required_sections_are_never_dropped_only_truncated() -> None:
    manager = ContextManager(token_budget=5)
    original_content = "word " * 500

    sections = [
        ContextSection("Only Section", original_content, Priority.CRITICAL, required=True),
    ]

    text, metadata = manager._assemble(
        "test-agent", sections, selected_file_count=0, documentation_section_count=0
    )

    assert "Only Section" in text
    assert metadata.dropped_sections == []
    assert metadata.truncated_sections == ["Only Section"]
    assert metadata.estimated_tokens < manager._count_tokens(original_content) / 10


def test_within_budget_context_is_assembled_unmodified() -> None:
    manager = ContextManager(token_budget=10_000)

    sections = [
        ContextSection("A", "short content", Priority.HIGH),
        ContextSection("B", "more short content", Priority.LOW),
    ]

    text, metadata = manager._assemble(
        "test-agent", sections, selected_file_count=0, documentation_section_count=0
    )

    assert "short content" in text
    assert "more short content" in text
    assert metadata.dropped_sections == []
    assert metadata.truncated_sections == []


def test_realistic_oversized_developer_repair_stays_within_budget() -> None:
    manager = ContextManager(token_budget=2000)
    state = WorkflowState()
    state.implementation.generated_code = [
        GeneratedCode(path=f"file_{i}.py", content="x = 1\n" * 2000, language="python")
        for i in range(10)
    ]
    state.execution.last_repair_trigger = RepairTrigger.TEST_FAILURE
    state.debug.root_cause = "A very specific root cause."
    state.debug.affected_files = ["file_0.py"]
    state.testing.stderr = "AssertionError: boom"

    text = manager.build_context(agent_name="developer", state=state)

    assert "A very specific root cause." in text
    assert "AssertionError: boom" in text
    assert manager.last_metadata.estimated_tokens <= manager.token_budget + 50




def _registry_with_tool(identity: str, description: str) -> MCPToolRegistry:
    registry = MCPToolRegistry()
    server_name, tool_name = identity.split(".", 1)
    registry.register_server_tools(
        server_name,
        [DiscoveredTool(identity=identity, server_name=server_name, tool_name=tool_name, description=description)],
    )
    return registry


def test_mcp_documentation_section_included_when_tools_available() -> None:
    manager = ContextManager()
    registry = _registry_with_tool("documentation.search_docs", "Searches project documentation.")

    text = manager.build_context(
        agent_name="documentation",
        state=WorkflowState(),
        mcp_registry=registry,
        mcp_tool_identities=["documentation.search_docs"],
    )

    assert "Available Tools" in text
    assert "documentation.search_docs" in text
    assert "Searches project documentation." in text


def test_filesystem_tool_grant_adds_project_folder_guidance() -> None:

    manager = ContextManager()
    registry = _registry_with_tool("filesystem.list_directory", "Lists a directory.")
    state = WorkflowState()
    state.project.output_directory = "C:/Users/naman/OneDrive/Desktop/agent/workspace/proj_20260725_3a8e9a94"

    text = manager.build_context(
        agent_name="tester",
        state=state,
        mcp_registry=registry,
        mcp_tool_identities=["filesystem.list_directory"],
    )

    assert "proj_20260725_3a8e9a94/" in text
    assert "never a bare 'backend'" in text


def test_cached_documentation_section_included_when_research_present() -> None:
    manager = ContextManager()
    state = WorkflowState()
    state.research.documentation["FastAPI"] = "FastAPI is built on Starlette and Pydantic."

    text = manager.build_context(agent_name="developer", state=state)

    assert "Cached Documentation" in text
    assert "### FastAPI" in text
    assert "FastAPI is built on Starlette and Pydantic." in text


def test_cached_documentation_section_absent_when_no_research() -> None:
    manager = ContextManager()

    text = manager.build_context(agent_name="developer", state=WorkflowState())

    assert "Cached Documentation" not in text


def test_cached_documentation_excerpt_is_capped_per_technology() -> None:
    manager = ContextManager()
    state = WorkflowState()
    state.research.documentation["Huge"] = "x" * 5000

    text = manager.build_context(agent_name="developer", state=state)

    assert "[truncated]" in text
    assert "x" * 5000 not in text


def test_no_filesystem_guidance_when_filesystem_not_granted() -> None:
    manager = ContextManager()
    registry = _registry_with_tool("context7.resolve-library-id", "Resolves a library id.")
    state = WorkflowState()
    state.project.output_directory = "C:/Users/naman/OneDrive/Desktop/agent/workspace/proj_20260725_3a8e9a94"

    text = manager.build_context(
        agent_name="architect",
        state=state,
        mcp_registry=registry,
        mcp_tool_identities=["context7.resolve-library-id"],
    )

    assert "never a bare 'backend'" not in text
    assert manager.last_metadata.documentation_section_count == 1


def test_mcp_documentation_section_absent_without_tools() -> None:
    manager = ContextManager()

    text = manager.build_context(agent_name="documentation", state=WorkflowState())

    assert "Available Documentation Tools" not in text
    assert manager.last_metadata.documentation_section_count == 0


def test_mcp_documentation_section_absent_when_identities_not_in_registry() -> None:
    manager = ContextManager()
    registry = MCPToolRegistry()

    text = manager.build_context(
        agent_name="documentation",
        state=WorkflowState(),
        mcp_registry=registry,
        mcp_tool_identities=["documentation.search_docs"],
    )

    assert "Available Documentation Tools" not in text




def test_empty_conversation_history_serializes_safely() -> None:
    manager = ContextManager()

    text = manager.build_context(agent_name="analysis", state=WorkflowState())

    assert "Conversation History" in text
    assert "No summary available." in text


def test_last_metadata_reflects_the_most_recent_call() -> None:
    manager = ContextManager()

    manager.build_context(agent_name="analysis", state=WorkflowState())
    first = manager.last_metadata

    manager.build_context(agent_name="planner", state=WorkflowState())
    second = manager.last_metadata

    assert first.agent_name == "analysis"
    assert second.agent_name == "planner"