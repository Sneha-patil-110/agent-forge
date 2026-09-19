from __future__ import annotations

import pytest

from backend.core.exceptions import KnowledgeEntryNotFoundError
from backend.services.knowledge_manager import KnowledgeManager
from backend.state.knowledge_state import KnowledgeCategory, KnowledgeStatus
from backend.state.workflow_state import WorkflowState


@pytest.fixture
def manager() -> KnowledgeManager:
    return KnowledgeManager()


@pytest.fixture
def state() -> WorkflowState:
    return WorkflowState()




def test_record_creates_an_active_entry(manager, state) -> None:
    entry = manager.record(
        state,
        category=KnowledgeCategory.ARCHITECTURE_DECISION,
        title="Repository Pattern",
        content="Use the repository pattern for data access.",
        created_by="architect",
        source_id="AD1",
    )

    assert entry.status == KnowledgeStatus.ACTIVE
    assert entry.created_by == "architect"
    assert entry.id
    assert state.knowledge.entries == [entry]


def test_record_with_same_source_id_is_idempotent(manager, state) -> None:
    first = manager.record(
        state,
        category=KnowledgeCategory.ARCHITECTURE_DECISION,
        title="Repository Pattern",
        content="Use the repository pattern.",
        created_by="architect",
        source_id="AD1",
    )
    second = manager.record(
        state,
        category=KnowledgeCategory.ARCHITECTURE_DECISION,
        title="Repository Pattern (restated)",
        content="Use the repository pattern.",
        created_by="architect",
        source_id="AD1",
    )

    assert first.id == second.id
    assert len(state.knowledge.entries) == 1


def test_record_without_source_id_dedupes_on_identical_content(manager, state) -> None:
    first = manager.record(
        state,
        category=KnowledgeCategory.CODING_STANDARD,
        title="Review Recommendation",
        content="Validate all user input.",
        created_by="reviewer",
    )
    second = manager.record(
        state,
        category=KnowledgeCategory.CODING_STANDARD,
        title="Review Recommendation",
        content="Validate all user input.",
        created_by="reviewer",
    )

    assert first.id == second.id
    assert len(state.knowledge.entries) == 1


def test_record_different_content_creates_separate_entries(manager, state) -> None:
    manager.record(
        state,
        category=KnowledgeCategory.CODING_STANDARD,
        title="Review Recommendation",
        content="Validate all user input.",
        created_by="reviewer",
    )
    manager.record(
        state,
        category=KnowledgeCategory.CODING_STANDARD,
        title="Review Recommendation",
        content="Use dependency injection consistently.",
        created_by="reviewer",
    )

    assert len(state.knowledge.entries) == 2


def test_record_same_content_different_category_is_not_deduped(manager, state) -> None:
    manager.record(
        state,
        category=KnowledgeCategory.CODING_STANDARD,
        title="A",
        content="shared text",
        created_by="reviewer",
    )
    manager.record(
        state,
        category=KnowledgeCategory.ASSUMPTION,
        title="B",
        content="shared text",
        created_by="architect",
    )

    assert len(state.knowledge.entries) == 2




def test_get_on_empty_store_returns_empty_list(manager, state) -> None:
    assert manager.get(state) == []


def test_get_filters_by_category(manager, state) -> None:
    manager.record(
        state,
        category=KnowledgeCategory.ARCHITECTURE_DECISION,
        title="A",
        content="a",
        created_by="architect",
    )
    manager.record(
        state,
        category=KnowledgeCategory.CODING_STANDARD,
        title="B",
        content="b",
        created_by="reviewer",
    )

    results = manager.get(state, categories=[KnowledgeCategory.CODING_STANDARD])

    assert [entry.title for entry in results] == ["B"]


def test_get_excludes_categories(manager, state) -> None:
    manager.record(
        state,
        category=KnowledgeCategory.ARCHITECTURE_DECISION,
        title="A",
        content="a",
        created_by="architect",
    )
    manager.record(
        state,
        category=KnowledgeCategory.CODING_STANDARD,
        title="B",
        content="b",
        created_by="reviewer",
    )

    results = manager.get(state, exclude_categories=[KnowledgeCategory.ARCHITECTURE_DECISION])

    assert [entry.title for entry in results] == ["B"]


def test_get_excludes_superseded_entries_by_default(manager, state) -> None:
    entry = manager.record(
        state,
        category=KnowledgeCategory.ASSUMPTION,
        title="Old",
        content="old fact",
        created_by="architect",
    )
    manager.replace(state, entry.id, title="New", content="new fact", created_by="architect")

    active = manager.get(state)

    assert [e.title for e in active] == ["New"]

    everything = manager.get(state, statuses=[KnowledgeStatus.ACTIVE, KnowledgeStatus.SUPERSEDED])
    assert {e.title for e in everything} == {"Old", "New"}




def test_update_modifies_title_and_content_in_place(manager, state) -> None:
    entry = manager.record(
        state,
        category=KnowledgeCategory.ASSUMPTION,
        title="Original",
        content="original content",
        created_by="architect",
    )

    updated = manager.update(state, entry.id, content="revised content")

    assert updated.id == entry.id
    assert updated.title == "Original"
    assert updated.content == "revised content"
    assert updated.updated_at >= updated.created_at
    assert len(state.knowledge.entries) == 1


def test_update_unknown_id_raises() -> None:
    manager = KnowledgeManager()
    state = WorkflowState()

    with pytest.raises(KnowledgeEntryNotFoundError):
        manager.update(state, "does-not-exist", content="x")




def test_replace_supersedes_the_old_entry_and_creates_a_new_one(manager, state) -> None:
    original = manager.record(
        state,
        category=KnowledgeCategory.ARCHITECTURE_DECISION,
        title="Repository Pattern",
        content="Use the repository pattern.",
        created_by="architect",
        source_id="AD1",
    )

    replacement = manager.replace(
        state,
        original.id,
        title="Repository + Unit of Work",
        content="Use the repository pattern with a unit of work.",
        created_by="architect",
    )

    assert replacement.id != original.id
    assert replacement.supersedes == original.id
    assert replacement.source_id == original.source_id
    assert replacement.status == KnowledgeStatus.ACTIVE

    stored_original = next(e for e in state.knowledge.entries if e.id == original.id)
    assert stored_original.status == KnowledgeStatus.SUPERSEDED

    active_titles = [e.title for e in manager.get(state, categories=[KnowledgeCategory.ARCHITECTURE_DECISION])]
    assert active_titles == ["Repository + Unit of Work"]


def test_replace_unknown_id_raises() -> None:
    manager = KnowledgeManager()
    state = WorkflowState()

    with pytest.raises(KnowledgeEntryNotFoundError):
        manager.replace(state, "does-not-exist", title="x", content="y", created_by="architect")