from __future__ import annotations

from backend.mcp.discovery import DiscoveredTool
from backend.mcp.registry import MCPToolRegistry
from backend.services.documentation_prefetch_service import DocumentationPrefetchService
from backend.state.workflow_state import WorkflowState


def _registry_with_context7() -> MCPToolRegistry:
    registry = MCPToolRegistry()
    registry.register_server_tools(
        "context7",
        [
            DiscoveredTool(
                identity="context7.resolve-library-id", server_name="context7", tool_name="resolve-library-id"
            ),
            DiscoveredTool(identity="context7.query-docs", server_name="context7", tool_name="query-docs"),
        ],
    )
    return registry


class _StubResult:
    def __init__(self, data: str | None) -> None:
        self.data = data


class _StubExecutor:

    def __init__(self, *, resolve_text: str | None, docs_text: str | None) -> None:
        self.resolve_text = resolve_text
        self.docs_text = docs_text
        self.calls: list[tuple[str, dict]] = []

    def execute(self, *, agent, tool_identity, arguments):
        self.calls.append((tool_identity, arguments))

        if tool_identity == "context7.resolve-library-id":
            return _StubResult(self.resolve_text)

        return _StubResult(self.docs_text)


_RESOLVE_TEXT = (
    "Available Libraries:\n\n"
    "- Title: FastAPI\n"
    "- Context7-compatible library ID: /websites/fastapi_tiangolo\n"
    "- Description: A web framework.\n"
)


def test_fetches_and_caches_docs_for_each_technology_once() -> None:
    executor = _StubExecutor(resolve_text=_RESOLVE_TEXT, docs_text="FastAPI is built on Starlette and Pydantic.")
    service = DocumentationPrefetchService(mcp_executor=executor, mcp_registry=_registry_with_context7())
    state = WorkflowState()
    state.project.tech_stack = ["FastAPI"]

    service.ensure_cached(state)

    assert state.research.documentation["FastAPI"] == "FastAPI is built on Starlette and Pydantic."
    assert [c[0] for c in executor.calls] == ["context7.resolve-library-id", "context7.query-docs"]
    assert executor.calls[1][1]["libraryId"] == "/websites/fastapi_tiangolo"


def test_does_not_refetch_an_already_cached_technology() -> None:
    executor = _StubExecutor(resolve_text=_RESOLVE_TEXT, docs_text="docs")
    service = DocumentationPrefetchService(mcp_executor=executor, mcp_registry=_registry_with_context7())
    state = WorkflowState()
    state.project.tech_stack = ["FastAPI"]
    state.research.documentation["FastAPI"] = "already fetched earlier this run"

    service.ensure_cached(state)

    assert executor.calls == []
    assert state.research.documentation["FastAPI"] == "already fetched earlier this run"


def test_skips_a_technology_with_no_library_match_without_failing_others() -> None:
    executor = _StubExecutor(resolve_text="No matches found.", docs_text="unused")
    service = DocumentationPrefetchService(mcp_executor=executor, mcp_registry=_registry_with_context7())
    state = WorkflowState()
    state.project.tech_stack = ["SomeObscureLibrary"]

    service.ensure_cached(state)

    assert state.research.documentation == {}
    assert [c[0] for c in executor.calls] == ["context7.resolve-library-id"]


def test_inert_when_context7_not_discovered() -> None:
    executor = _StubExecutor(resolve_text=_RESOLVE_TEXT, docs_text="docs")
    service = DocumentationPrefetchService(mcp_executor=executor, mcp_registry=MCPToolRegistry())
    state = WorkflowState()
    state.project.tech_stack = ["FastAPI"]

    service.ensure_cached(state)

    assert state.research.documentation == {}
    assert executor.calls == []


def test_inert_when_executor_is_none() -> None:
    service = DocumentationPrefetchService(mcp_executor=None, mcp_registry=_registry_with_context7())
    state = WorkflowState()
    state.project.tech_stack = ["FastAPI"]

    service.ensure_cached(state)

    assert state.research.documentation == {}


def test_empty_tech_stack_is_a_no_op() -> None:
    executor = _StubExecutor(resolve_text=_RESOLVE_TEXT, docs_text="docs")
    service = DocumentationPrefetchService(mcp_executor=executor, mcp_registry=_registry_with_context7())
    state = WorkflowState()

    service.ensure_cached(state)

    assert executor.calls == []
