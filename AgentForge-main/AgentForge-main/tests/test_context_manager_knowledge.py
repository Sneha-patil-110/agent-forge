from __future__ import annotations

from backend.services.context_manager import ContextManager
from backend.state.knowledge_state import KnowledgeCategory
from backend.state.workflow_state import WorkflowState


def test_knowledge_section_included_for_integrated_agents() -> None:
    manager = ContextManager()
    state = WorkflowState()
    manager.knowledge_manager.record(
        state,
        category=KnowledgeCategory.CODING_STANDARD,
        title="Naming convention",
        content="Use snake_case for functions.",
        created_by="reviewer",
    )

    for agent_name in ("planner", "architect", "developer", "reviewer", "documentation"):
        text = manager.build_context(agent_name=agent_name, state=state)
        assert "Project Knowledge" in text, agent_name
        assert "Naming convention" in text, agent_name


def test_knowledge_section_absent_for_non_integrated_agents() -> None:
    manager = ContextManager()
    state = WorkflowState()
    manager.knowledge_manager.record(
        state,
        category=KnowledgeCategory.CODING_STANDARD,
        title="Naming convention",
        content="Use snake_case for functions.",
        created_by="reviewer",
    )

    for agent_name in ("analysis", "tester", "debugger"):
        text = manager.build_context(agent_name=agent_name, state=state)
        assert "Project Knowledge" not in text, agent_name


def test_architecture_decisions_are_excluded_from_the_knowledge_section() -> None:

    manager = ContextManager()
    state = WorkflowState()
    manager.knowledge_manager.record(
        state,
        category=KnowledgeCategory.ARCHITECTURE_DECISION,
        title="Repository Pattern",
        content="Use the repository pattern for data access.",
        created_by="architect",
        source_id="AD1",
    )

    text = manager.build_context(agent_name="developer", state=state)

    assert "Project Knowledge" not in text
    assert manager.last_metadata.knowledge_entries_included == 0


def test_knowledge_section_absent_when_store_is_empty() -> None:
    manager = ContextManager()

    text = manager.build_context(agent_name="developer", state=WorkflowState())

    assert "Project Knowledge" not in text
    assert manager.last_metadata.knowledge_entries_included == 0


def test_superseded_entries_are_not_surfaced_in_context() -> None:
    manager = ContextManager()
    state = WorkflowState()
    entry = manager.knowledge_manager.record(
        state,
        category=KnowledgeCategory.ASSUMPTION,
        title="Old assumption",
        content="Users authenticate with email only.",
        created_by="architect",
    )
    manager.knowledge_manager.replace(
        state,
        entry.id,
        title="Updated assumption",
        content="Users authenticate with email or OAuth.",
        created_by="architect",
    )

    text = manager.build_context(agent_name="architect", state=state)

    assert "Users authenticate with email or OAuth." in text
    assert "Users authenticate with email only." not in text


def test_shared_knowledge_manager_instance_is_used_by_default() -> None:
    manager = ContextManager()

    assert manager.knowledge_manager is not None