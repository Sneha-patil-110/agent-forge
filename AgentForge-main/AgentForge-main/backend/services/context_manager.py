from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import TYPE_CHECKING, Callable

import tiktoken

from backend.core.constants import DEFAULT_CONTEXT_TOKEN_BUDGET
from backend.services.knowledge_manager import KnowledgeManager
from backend.state.execution_state import RepairTrigger
from backend.state.implementation_state import GeneratedCode
from backend.state.knowledge_state import KnowledgeCategory
from backend.state.workflow_state import WorkflowState

if TYPE_CHECKING:
    from backend.mcp.registry import MCPToolRegistry

logger = logging.getLogger(__name__)

_ENCODING = tiktoken.get_encoding("cl100k_base")


class Priority(IntEnum):

    CRITICAL = 0
    HIGH = 1
    MEDIUM = 2
    LOW = 3


@dataclass
class ContextSection:
    title: str
    content: str
    priority: Priority
    required: bool = False


@dataclass
class ContextMetadata:

    agent_name: str
    total_chars: int
    estimated_tokens: int
    section_count: int
    dropped_sections: list[str] = field(default_factory=list)
    truncated_sections: list[str] = field(default_factory=list)
    selected_file_count: int = 0
    documentation_section_count: int = 0
    knowledge_entries_included: int = 0


class ContextManager:
    _KNOWLEDGE_INTEGRATED_AGENTS = frozenset(
        {"planner", "architect", "developer", "reviewer", "documentation"}
    )

    _KNOWLEDGE_EXCLUDED_CATEGORIES = frozenset({KnowledgeCategory.ARCHITECTURE_DECISION})

    def __init__(
        self,
        *,
        token_budget: int = DEFAULT_CONTEXT_TOKEN_BUDGET,
        knowledge_manager: KnowledgeManager | None = None,
    ) -> None:
        self.token_budget = token_budget
        self.knowledge_manager = knowledge_manager or KnowledgeManager()
        self.last_metadata: ContextMetadata | None = None

    def build_context(
        self,
        *,
        agent_name: str,
        state: WorkflowState,
        mcp_registry: "MCPToolRegistry | None" = None,
        mcp_tool_identities: list[str] | None = None,
    ) -> str:
        builder = self._BUILDERS.get(agent_name)

        if builder is None:
            raise ValueError(
                f"No context builder registered for agent '{agent_name}'."
            )

        selected_file_count = 0
        sections, selected_file_count = builder(self, state)

        if agent_name != "analysis" and len(state.conversation.messages) > 1:
            latest_request = state.conversation.messages[-1].content

            if isinstance(latest_request, str) and latest_request.strip():
                sections = [
                    *sections,
                    ContextSection(
                        "Latest Follow-up Request",
                        latest_request.strip(),
                        Priority.HIGH,
                    ),
                ]

        mcp_tools_section = self._build_mcp_tools_section(mcp_registry, mcp_tool_identities, state)
        documentation_section_count = 0

        if mcp_tools_section is not None:
            sections = [*sections, mcp_tools_section]
            documentation_section_count = 1

        cached_docs_section = self._build_cached_documentation_section(state)

        if cached_docs_section is not None:
            sections = [*sections, cached_docs_section]

        knowledge_entries_included = 0

        if agent_name in self._KNOWLEDGE_INTEGRATED_AGENTS:
            knowledge_section, knowledge_entries_included = self._build_knowledge_section(state)

            if knowledge_section is not None:
                sections = [*sections, knowledge_section]

        text, metadata = self._assemble(
            agent_name,
            sections,
            selected_file_count=selected_file_count,
            documentation_section_count=documentation_section_count,
            knowledge_entries_included=knowledge_entries_included,
        )

        self.last_metadata = metadata

        logger.debug(
            "Context assembled for '%s': %d chars (~%d tokens), %d section(s) "
            "(%d dropped, %d truncated), %d file(s), %d doc section(s), %d knowledge entries",
            agent_name,
            metadata.total_chars,
            metadata.estimated_tokens,
            metadata.section_count,
            len(metadata.dropped_sections),
            len(metadata.truncated_sections),
            metadata.selected_file_count,
            metadata.documentation_section_count,
            metadata.knowledge_entries_included,
        )

        return text


    def _build_analysis_context(
        self, state: WorkflowState
    ) -> tuple[list[ContextSection], int]:
        conversation_history = [
            {"type": message.type, "content": message.content}
            for message in state.conversation.messages
        ]

        sections = [
            ContextSection(
                "Conversation History",
                json.dumps(conversation_history, indent=2, ensure_ascii=False),
                Priority.HIGH,
                required=True,
            ),
            ContextSection(
                "Conversation Summary",
                state.conversation.summary or "No summary available.",
                Priority.HIGH,
            ),
            ContextSection(
                "Current Project State",
                state.project.model_dump_json(indent=2),
                Priority.HIGH,
            ),
        ]

        return sections, 0

    def _build_planner_context(
        self, state: WorkflowState
    ) -> tuple[list[ContextSection], int]:
        sections = [
            ContextSection(
                "Project Information", state.project.model_dump_json(indent=2), Priority.HIGH
            ),
            ContextSection(
                "Conversation Summary",
                state.conversation.summary or "No summary available.",
                Priority.MEDIUM,
            ),
            ContextSection(
                "Existing Planning Information",
                state.planning.model_dump_json(indent=2),
                Priority.HIGH,
                required=True,
            ),
        ]

        return sections, 0

    def _build_architect_context(
        self, state: WorkflowState
    ) -> tuple[list[ContextSection], int]:
        sections = [
            ContextSection(
                "Project Information", state.project.model_dump_json(indent=2), Priority.HIGH
            ),
            ContextSection(
                "Planning Information",
                state.planning.model_dump_json(indent=2),
                Priority.HIGH,
                required=True,
            ),
        ]

        return sections, 0

    def _build_developer_context(
        self, state: WorkflowState
    ) -> tuple[list[ContextSection], int]:
        execution = state.execution
        feedback_sections: list[ContextSection] = []
        relevant_paths: set[str] = set()

        if execution.last_repair_trigger in (
            RepairTrigger.TEST_FAILURE,
            RepairTrigger.STATIC_VALIDATION_FAILURE,
            RepairTrigger.REVIEW_FEEDBACK,
            RepairTrigger.REPOSITORY_COMPLETENESS_FAILURE,
            RepairTrigger.DEPENDENCY_RESOLUTION_FAILURE,
        ):
            relevant_paths = set(state.debug.affected_files) | {
                change.file_path for change in state.debug.suggested_changes
            }
            evidence_section = (
                ContextSection(
                    "Review Feedback Evidence (what Debugger's analysis above is based on)",
                    state.review.model_dump_json(indent=2),
                    Priority.HIGH,
                )
                if execution.last_repair_trigger == RepairTrigger.REVIEW_FEEDBACK
                else ContextSection(
                    "Failed Test Execution Evidence (what Debugger's analysis above is based on)",
                    state.testing.model_dump_json(indent=2),
                    Priority.HIGH,
                )
            )
            feedback_sections = [
                ContextSection(
                    "Debug Feedback (fix the reported failure; preserve every "
                    "other valid existing generated file unless the repair "
                    "requires changing it)",
                    state.debug.model_dump_json(indent=2),
                    Priority.CRITICAL,
                    required=True,
                ),
                evidence_section,
            ]

        selected_files = self._select_relevant_files(
            state.implementation.generated_code, relevant_paths=relevant_paths
        )
        implementation_view = state.implementation.model_copy(
            update={"generated_code": selected_files}
        )

        sections = [
            ContextSection(
                "Project Information", state.project.model_dump_json(indent=2), Priority.HIGH
            ),
            ContextSection(
                "Planning Information", state.planning.model_dump_json(indent=2), Priority.HIGH
            ),
            ContextSection(
                "Architecture Information",
                state.architecture.model_dump_json(indent=2),
                Priority.HIGH,
            ),
            ContextSection(
                "Existing Implementation Information",
                implementation_view.model_dump_json(indent=2),
                Priority.MEDIUM,
            ),
            *feedback_sections,
        ]

        return sections, len(selected_files)

    def _build_tester_context(
        self, state: WorkflowState
    ) -> tuple[list[ContextSection], int]:
        sections = [
            ContextSection(
                "Project Information (requirements)", state.project.model_dump_json(indent=2), Priority.MEDIUM
            ),
            ContextSection(
                "Architecture Information (the intended contract)",
                state.architecture.model_dump_json(indent=2),
                Priority.HIGH,
                required=True,
            ),
            ContextSection(
                "Implementation Information",
                state.implementation.model_dump_json(indent=2),
                Priority.HIGH,
                required=True,
            ),
            ContextSection(
                "Test Execution Evidence (real, already captured -- never fabricate or alter this)",
                state.testing.model_dump_json(indent=2),
                Priority.CRITICAL,
                required=True,
            ),
        ]

        return sections, len(state.implementation.generated_code)


    def _build_reviewer_context(
        self, state: WorkflowState
    ) -> tuple[list[ContextSection], int]:
        sections = [
            ContextSection(
                "Project Information", state.project.model_dump_json(indent=2), Priority.MEDIUM
            ),
            ContextSection(
                "Planning Information", state.planning.model_dump_json(indent=2), Priority.LOW
            ),
            ContextSection(
                "Architecture Information",
                state.architecture.model_dump_json(indent=2),
                Priority.MEDIUM,
            ),
            ContextSection(
                "Implementation Information",
                state.implementation.model_dump_json(indent=2),
                Priority.HIGH,
                required=True,
            ),
            ContextSection(
                "Existing Review Information",
                state.review.model_dump_json(indent=2),
                Priority.HIGH,
            ),
        ]

        return sections, len(state.implementation.generated_code)

    def _build_documentation_context(
        self, state: WorkflowState
    ) -> tuple[list[ContextSection], int]:
        sections = [
            ContextSection(
                "Project Information", state.project.model_dump_json(indent=2), Priority.MEDIUM
            ),
            ContextSection(
                "Planning Information", state.planning.model_dump_json(indent=2), Priority.LOW
            ),
            ContextSection(
                "Architecture Information",
                state.architecture.model_dump_json(indent=2),
                Priority.MEDIUM,
            ),
            ContextSection(
                "Implementation Information",
                state.implementation.model_dump_json(indent=2),
                Priority.HIGH,
                required=True,
            ),
            ContextSection(
                "Review Information", state.review.model_dump_json(indent=2), Priority.MEDIUM
            ),
        ]

        return sections, len(state.implementation.generated_code)

    def _build_debugger_context(
        self, state: WorkflowState
    ) -> tuple[list[ContextSection], int]:
        is_review_triggered = state.execution.last_repair_trigger == RepairTrigger.REVIEW_FEEDBACK

        evidence_section = (
            ContextSection(
                "Real Review Feedback (from the Reviewer agent)",
                state.review.model_dump_json(indent=2),
                Priority.CRITICAL,
                required=True,
            )
            if is_review_triggered
            else ContextSection(
                "Real Test Execution Evidence",
                state.testing.model_dump_json(indent=2),
                Priority.CRITICAL,
                required=True,
            )
        )

        sections = [
            ContextSection(
                "Project Information", state.project.model_dump_json(indent=2), Priority.MEDIUM
            ),
            ContextSection(
                "Architecture Information",
                state.architecture.model_dump_json(indent=2),
                Priority.MEDIUM,
            ),
            ContextSection(
                "Implementation Information",
                state.implementation.model_dump_json(indent=2),
                Priority.HIGH,
                required=True,
            ),
            evidence_section,
        ]

        if not is_review_triggered and state.tester_analysis.classification is not None:
            sections.append(
                ContextSection(
                    "Tester's Analysis (already determined whether this is an "
                    "application code bug or a generated test bug -- weigh this, "
                    "don't re-guess from scratch)",
                    state.tester_analysis.model_dump_json(indent=2),
                    Priority.HIGH,
                    required=True,
                )
            )

        if state.debug.failure_summary or state.debug.root_cause:
            sections.append(
                ContextSection(
                    "Previous Debug Analysis (this failure has already been "
                    "analyzed once; note whether the same root cause "
                    "persists or a new failure appeared)",
                    state.debug.model_dump_json(indent=2),
                    Priority.MEDIUM,
                )
            )

        return sections, len(state.implementation.generated_code)

    _BUILDERS: dict[str, Callable[["ContextManager", WorkflowState], tuple[list[ContextSection], int]]] = {
        "analysis": _build_analysis_context,
        "planner": _build_planner_context,
        "architect": _build_architect_context,
        "developer": _build_developer_context,
        "tester": _build_tester_context,
        "reviewer": _build_reviewer_context,
        "documentation": _build_documentation_context,
        "debugger": _build_debugger_context,
    }


    @staticmethod
    def _select_relevant_files(
        generated_code: list[GeneratedCode],
        *,
        relevant_paths: set[str],
    ) -> list[GeneratedCode]:

        if not relevant_paths:
            return list(generated_code)

        selected = [file for file in generated_code if file.path in relevant_paths]

        return selected or list(generated_code)


    @staticmethod
    def _build_mcp_tools_section(
        mcp_registry: "MCPToolRegistry | None",
        mcp_tool_identities: list[str] | None,
        state: WorkflowState,
    ) -> ContextSection | None:

        if not mcp_registry or not mcp_tool_identities:
            return None

        lines = []
        has_filesystem_tool = False

        for identity in mcp_tool_identities:
            if not mcp_registry.has(identity):
                continue

            tool = mcp_registry.get(identity)
            lines.append(f"- {tool.identity}: {tool.description or 'No description available.'}")

            if tool.server_name == "filesystem":
                has_filesystem_tool = True

        if not lines:
            return None

        if has_filesystem_tool and state.project.output_directory:
            project_folder = Path(state.project.output_directory).name
            lines.append(
                f"\nFilesystem tool paths are relative to the shared workspace root, "
                f"which holds one folder per project. This project's own files are "
                f"under '{project_folder}/' -- e.g. use '{project_folder}/src', "
                f"never a bare 'backend'."
            )

        return ContextSection(
            "Available Tools",
            "\n".join(lines),
            Priority.MEDIUM,
        )

    _CACHED_DOC_EXCERPT_CHARS = 2000

    @classmethod
    def _build_cached_documentation_section(cls, state: WorkflowState) -> ContextSection | None:

        documentation = state.research.documentation

        if not documentation:
            return None

        blocks = []

        for technology, text in documentation.items():
            excerpt = text[: cls._CACHED_DOC_EXCERPT_CHARS]

            if len(text) > cls._CACHED_DOC_EXCERPT_CHARS:
                excerpt += "... [truncated]"

            blocks.append(f"### {technology}\n{excerpt}")

        return ContextSection(
            "Cached Documentation",
            "\n\n".join(blocks),
            Priority.MEDIUM,
        )


    def _build_knowledge_section(
        self, state: WorkflowState
    ) -> tuple[ContextSection | None, int]:

        entries = self.knowledge_manager.get(
            state, exclude_categories=self._KNOWLEDGE_EXCLUDED_CATEGORIES
        )

        if not entries:
            return None, 0

        lines = [f"- [{entry.category.value}] {entry.title}: {entry.content}" for entry in entries]

        section = ContextSection(
            "Project Knowledge",
            "\n".join(lines),
            Priority.MEDIUM,
        )

        return section, len(entries)


    def _assemble(
        self,
        agent_name: str,
        sections: list[ContextSection],
        *,
        selected_file_count: int,
        documentation_section_count: int,
        knowledge_entries_included: int = 0,
    ) -> tuple[str, ContextMetadata]:
        contents = [section.content for section in sections]
        tokens = [self._count_tokens(content) for content in contents]
        total_tokens = sum(tokens)
        kept = list(range(len(sections)))

        dropped: list[str] = []

        if total_tokens > self.token_budget:
            drop_order = sorted(
                (index for index in kept if not sections[index].required),
                key=lambda index: (-sections[index].priority, -tokens[index]),
            )

            for index in drop_order:
                if total_tokens <= self.token_budget:
                    break

                kept.remove(index)
                total_tokens -= tokens[index]
                dropped.append(sections[index].title)

        truncated: list[str] = []

        if total_tokens > self.token_budget and kept:
            largest_index = max(kept, key=lambda index: tokens[index])
            overflow = total_tokens - self.token_budget
            target_tokens = max(tokens[largest_index] - overflow, 0)

            new_content = self._truncate_content(contents[largest_index], target_tokens)
            new_tokens = self._count_tokens(new_content)

            total_tokens += new_tokens - tokens[largest_index]
            contents[largest_index] = new_content
            tokens[largest_index] = new_tokens
            truncated.append(sections[largest_index].title)

        kept.sort()

        text = "\n\n".join(
            f"{sections[index].title}\n\n{contents[index]}"
            for index in kept
            if contents[index].strip()
        )

        metadata = ContextMetadata(
            agent_name=agent_name,
            total_chars=len(text),
            estimated_tokens=total_tokens,
            section_count=len(kept),
            dropped_sections=dropped,
            truncated_sections=truncated,
            selected_file_count=selected_file_count,
            documentation_section_count=documentation_section_count,
            knowledge_entries_included=knowledge_entries_included,
        )

        return text, metadata

    @staticmethod
    def _count_tokens(text: str) -> int:
        if not text:
            return 0

        return len(_ENCODING.encode(text))

    _TRUNCATION_MARKER = "\n\n[... truncated to fit the context token budget ...]"

    @classmethod
    def _truncate_content(cls, content: str, target_tokens: int) -> str:
        token_ids = _ENCODING.encode(content)

        if len(token_ids) <= target_tokens:
            return content

        marker_tokens = cls._count_tokens(cls._TRUNCATION_MARKER)
        content_budget = target_tokens - marker_tokens

        if content_budget <= 0:
            return "[omitted: exceeds the context token budget]"

        truncated_text = _ENCODING.decode(token_ids[:content_budget])

        return truncated_text + cls._TRUNCATION_MARKER