from __future__ import annotations

import logging
import secrets
import time
from datetime import UTC, datetime
from typing import Iterable

from backend.core.exceptions import KnowledgeEntryNotFoundError
from backend.state.knowledge_state import (
    KnowledgeCategory,
    KnowledgeEntry,
    KnowledgeState,
    KnowledgeStatus,
)
from backend.state.workflow_state import WorkflowState

logger = logging.getLogger(__name__)

_DEFAULT_STATUSES = (KnowledgeStatus.ACTIVE,)


class KnowledgeManager:
    def record(
        self,
        state: WorkflowState,
        *,
        category: KnowledgeCategory,
        title: str,
        content: str,
        created_by: str,
        source_id: str | None = None,
    ) -> KnowledgeEntry:

        existing = self._find_duplicate(
            state.knowledge, category=category, source_id=source_id, content=content
        )

        if existing is not None:
            return existing

        entry = KnowledgeEntry(
            id=self._generate_id(),
            category=category,
            title=title,
            content=content,
            created_by=created_by,
            source_id=source_id,
        )

        state.knowledge.entries.append(entry)

        logger.debug(
            "Knowledge recorded: [%s] '%s' by %s (id=%s)",
            category.value,
            title,
            created_by,
            entry.id,
        )

        return entry

    def get(
        self,
        state: WorkflowState,
        *,
        categories: Iterable[KnowledgeCategory] | None = None,
        exclude_categories: Iterable[KnowledgeCategory] | None = None,
        statuses: Iterable[KnowledgeStatus] = _DEFAULT_STATUSES,
    ) -> list[KnowledgeEntry]:
        started_at = time.perf_counter()

        include_set = set(categories) if categories is not None else None
        exclude_set = set(exclude_categories) if exclude_categories is not None else set()
        status_set = set(statuses)

        results = [
            entry
            for entry in state.knowledge.entries
            if entry.status in status_set
            and entry.category not in exclude_set
            and (include_set is None or entry.category in include_set)
        ]

        logger.debug(
            "Knowledge retrieved: %d entr%s in %.3fms",
            len(results),
            "y" if len(results) == 1 else "ies",
            (time.perf_counter() - started_at) * 1000,
        )

        return results

    def update(
        self,
        state: WorkflowState,
        entry_id: str,
        *,
        title: str | None = None,
        content: str | None = None,
    ) -> KnowledgeEntry:

        entry = self._get_by_id(state.knowledge, entry_id)

        if title is not None:
            entry.title = title

        if content is not None:
            entry.content = content

        entry.updated_at = datetime.now(UTC)

        return entry

    def replace(
        self,
        state: WorkflowState,
        entry_id: str,
        *,
        title: str,
        content: str,
        created_by: str,
    ) -> KnowledgeEntry:

        old_entry = self._get_by_id(state.knowledge, entry_id)
        old_entry.status = KnowledgeStatus.SUPERSEDED
        old_entry.updated_at = datetime.now(UTC)

        new_entry = KnowledgeEntry(
            id=self._generate_id(),
            category=old_entry.category,
            title=title,
            content=content,
            created_by=created_by,
            source_id=old_entry.source_id,
            supersedes=old_entry.id,
        )

        state.knowledge.entries.append(new_entry)

        logger.debug(
            "Knowledge replaced: id=%s -> id=%s ('%s')", old_entry.id, new_entry.id, title
        )

        return new_entry

    @staticmethod
    def _find_duplicate(
        knowledge_state: KnowledgeState,
        *,
        category: KnowledgeCategory,
        source_id: str | None,
        content: str,
    ) -> KnowledgeEntry | None:
        for entry in knowledge_state.entries:
            if entry.status != KnowledgeStatus.ACTIVE or entry.category != category:
                continue

            if source_id is not None:
                if entry.source_id == source_id:
                    return entry
            elif entry.source_id is None and entry.content == content:
                return entry

        return None

    @staticmethod
    def _get_by_id(knowledge_state: KnowledgeState, entry_id: str) -> KnowledgeEntry:
        for entry in knowledge_state.entries:
            if entry.id == entry_id:
                return entry

        raise KnowledgeEntryNotFoundError(
            f"Knowledge entry '{entry_id}' was not found.",
            details={"entry_id": entry_id},
        )

    @staticmethod
    def _generate_id() -> str:
        return secrets.token_hex(6)