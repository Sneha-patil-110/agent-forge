from __future__ import annotations

import asyncio
import logging
import shutil
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Awaitable, TypeVar

from langchain_core.messages import AIMessage, HumanMessage

from backend.agents.analysis_agent import AnalysisAgent
from backend.agents.architect_agent import ArchitectAgent
from backend.agents.debugger_agent import DebuggerAgent
from backend.agents.developer_agent import DeveloperAgent
from backend.agents.documenter_agent import DocumentationAgent
from backend.agents.planner_agent import PlannerAgent
from backend.agents.reviewer_agent import ReviewerAgent
from backend.agents.tester_agent import TesterAgent

from backend.core.exceptions import RunCorruptedError
from backend.core.failure_classification import classify_exception
from backend.core.logging import setup_logging
from backend.core.workspace import WORKSPACE_ROOT
from backend.db.base import create_db_engine, session_factory_for

from backend.events.dispatcher import EventDispatcher
from backend.events.event_types import EventType, WorkflowEvent

from backend.graph.builder import WorkflowBuilder
from backend.graph.nodes import WorkflowNodes

from backend.llms.model_registry import ModelRegistry

from backend.mcp.cache import load_tool_cache
from backend.mcp.client_manager import MCPClientManager
from backend.mcp.config import build_capability_map, load_mcp_server_configs
from backend.mcp.executor import MCPToolExecutor, set_current_run_id
from backend.mcp.metrics import MCPMetricsCollector
from backend.mcp.permissions import MCPPermissionPolicy
from backend.mcp.registry import MCPToolRegistry

from backend.repositories.project_repository import ProjectRepository
from backend.services.auth_service import AuthService
from backend.services.checkpoint_service import CheckpointService
from backend.services.context_manager import ContextManager
from backend.services.db_sync_service import DatabaseSyncService
from backend.services.dependency_preparation_service import DependencyPreparationService
from backend.services.documentation_prefetch_service import DocumentationPrefetchService
from backend.services.environment_preflight_service import EnvironmentPreflightService
from backend.services.failure_bundle_service import FailureBundleService
from backend.services.knowledge_manager import KnowledgeManager
from backend.services.llm_service import LLMService
from backend.services.materialization_service import MaterializationService
from backend.services.static_validation_service import StaticValidationService
from backend.services.test_discovery_service import TestDiscoveryService
from backend.services.mcp_management_service import MCPManagementService
from backend.services.prompt_service import PromptService
from backend.services.rate_limiter import RateLimiter
from backend.services.repository_completeness_service import RepositoryCompletenessService
from backend.services.repository_integrity_validator import RepositoryIntegrityValidator
from backend.services.repository_service import RepositoryService

from backend.services.run_service import RunService
from backend.services.testing_service import TestingService
from backend.services.tracing_service import TracingService

from backend.state.execution_state import AgentType, RepairTrigger, WorkflowStatus
from backend.state.workflow_state import WorkflowState

from backend.utils.project_id import generate_project_id

from backend.tools.filesystem_tool import FilesystemTool
from backend.tools.git_tool import GitTool
from backend.tools.search_tool import SearchTool
from backend.tools.terminal_tool import TerminalTool
from backend.tools.tool_registry import ToolRegistry

_INVOKE_RECURSION_LIMIT = 100


PROMPT_DIRECTORY = (
    Path(__file__).resolve().parent.parent / "prompts"
)

logger = logging.getLogger(__name__)

_T = TypeVar("_T")


def _run_async(coro: Awaitable[_T]) -> _T:

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    box: dict[str, Any] = {}

    def _runner() -> None:
        try:
            box["value"] = asyncio.run(coro)
        except BaseException as error:
            box["error"] = error

    thread = threading.Thread(target=_runner)
    thread.start()
    thread.join()

    if "error" in box:
        raise box["error"]

    return box["value"]


def _synthesize_assistant_reply(state: WorkflowState) -> str:

    file_count = len(state.implementation.written_files)
    parts = [f"Updated {file_count} file{'s' if file_count != 1 else ''}."]

    if state.testing.passed:
        parts.append("Tests passed.")
    elif state.testing.failed_tests:
        parts.append("Some tests failed.")

    if state.review.passed:
        parts.append(f"Review passed (score {state.review.score:.1f}/10).")

    doc_titles = [doc.title for doc in state.documentation.generated_docs]

    if doc_titles:
        parts.append("Documentation: " + ", ".join(doc_titles) + ".")

    return " ".join(parts)


class Application:
    def __init__(self) -> None:
        setup_logging()

        self._resuming_runs: set[str] = set()
        self._resume_lock = threading.Lock()

        self.prompt_service = PromptService(
            PROMPT_DIRECTORY
        )

        self.tracing_service = TracingService()

        self.knowledge_manager = KnowledgeManager()

        self.context_manager = ContextManager(knowledge_manager=self.knowledge_manager)

        self.model_registry = ModelRegistry()

        self.llm_service = LLMService(
            self.model_registry,
            tracing_service=self.tracing_service,
        )

        self.tool_registry = ToolRegistry()

        self._register_tools()

        self.materialization_service = MaterializationService(
            self.tool_registry
        )

        self.testing_service = TestingService(
            self.tool_registry
        )

        self.test_discovery_service = TestDiscoveryService()

        self.environment_preflight_service = EnvironmentPreflightService()

        self.repository_integrity_validator = RepositoryIntegrityValidator()

        self.repository_completeness_service = RepositoryCompletenessService()

        self.dependency_preparation_service = DependencyPreparationService(
            self.tool_registry
        )

        self.failure_bundle_service = FailureBundleService()

        self.mcp_metrics = MCPMetricsCollector()

        mcp_configs = load_mcp_server_configs()

        self.mcp_client_manager = MCPClientManager(mcp_configs, metrics=self.mcp_metrics)

        self.mcp_tool_registry = MCPToolRegistry()

        self._discover_mcp_tools()

        self.mcp_management_service = MCPManagementService(
            client_manager=self.mcp_client_manager,
            tool_registry=self.mcp_tool_registry,
        )

        capability_map = build_capability_map(mcp_configs)

        self.mcp_permission_policy = MCPPermissionPolicy(
            {
                AgentType.ANALYSIS: frozenset(),
                AgentType.PLANNER: frozenset({"sequential-thinking.*"}),
                AgentType.ARCHITECT: frozenset({"context7.*"}),
                AgentType.DEVELOPER: frozenset({
                    "github.*", "context7.*", "postgres.*", "exa.*", "filesystem:read",
                }),
                AgentType.TESTER: frozenset(),
                AgentType.DEBUGGER: frozenset({"context7.*", "github.*", "exa.*", "playwright.*"}),
                AgentType.REVIEWER: frozenset({"context7.*", "github.*", "sequential-thinking.*"}),
                AgentType.DOCUMENTATION: frozenset({"context7.*", "exa.*"}),
            },
            capability_map=capability_map,
        )

        self.mcp_fallback_map: dict[str, list[str]] = {
            "context7": ["exa"],
            "github": ["exa"],
        }

        self.event_dispatcher = EventDispatcher()

        self.mcp_tool_executor = MCPToolExecutor(
            client_manager=self.mcp_client_manager,
            registry=self.mcp_tool_registry,
            permission_policy=self.mcp_permission_policy,
            event_dispatcher=self.event_dispatcher,
            tracing_service=self.tracing_service,
            metrics=self.mcp_metrics,
        )

        self.documentation_prefetch_service = DocumentationPrefetchService(
            mcp_executor=self.mcp_tool_executor,
            mcp_registry=self.mcp_tool_registry,
        )

        def _mcp_kwargs(agent_type: AgentType) -> dict:
            return {
                "mcp_executor": self.mcp_tool_executor,
                "mcp_registry": self.mcp_tool_registry,
                "mcp_tool_identities": self.mcp_permission_policy.allowed_identities(
                    agent_type, self.mcp_tool_registry
                ),
                "mcp_fallback_map": self.mcp_fallback_map,
            }

        self.analysis_agent = AnalysisAgent(
            self.prompt_service,
            self.llm_service,
            context_manager=self.context_manager,
            knowledge_manager=self.knowledge_manager,
            **_mcp_kwargs(AgentType.ANALYSIS),
        )

        self.planner_agent = PlannerAgent(
            self.prompt_service,
            self.llm_service,
            context_manager=self.context_manager,
            knowledge_manager=self.knowledge_manager,
            **_mcp_kwargs(AgentType.PLANNER),
        )

        self.architect_agent = ArchitectAgent(
            self.prompt_service,
            self.llm_service,
            context_manager=self.context_manager,
            knowledge_manager=self.knowledge_manager,
            **_mcp_kwargs(AgentType.ARCHITECT),
        )

        self.developer_agent = DeveloperAgent(
            self.prompt_service,
            self.llm_service,
            context_manager=self.context_manager,
            knowledge_manager=self.knowledge_manager,
            **_mcp_kwargs(AgentType.DEVELOPER),
        )

        self.tester_agent = TesterAgent(
            self.prompt_service,
            self.llm_service,
            context_manager=self.context_manager,
            knowledge_manager=self.knowledge_manager,
            **_mcp_kwargs(AgentType.TESTER),
        )

        self.debugger_agent = DebuggerAgent(
            self.prompt_service,
            self.llm_service,
            context_manager=self.context_manager,
            knowledge_manager=self.knowledge_manager,
            **_mcp_kwargs(AgentType.DEBUGGER),
        )

        self.reviewer_agent = ReviewerAgent(
            self.prompt_service,
            self.llm_service,
            context_manager=self.context_manager,
            knowledge_manager=self.knowledge_manager,
            **_mcp_kwargs(AgentType.REVIEWER),
        )

        self.documentation_agent = DocumentationAgent(
            self.prompt_service,
            self.llm_service,
            context_manager=self.context_manager,
            knowledge_manager=self.knowledge_manager,
            **_mcp_kwargs(AgentType.DOCUMENTATION),
        )

        self.nodes = WorkflowNodes(
            analysis_agent=self.analysis_agent,
            planner_agent=self.planner_agent,
            architect_agent=self.architect_agent,
            developer_agent=self.developer_agent,
            tester_agent=self.tester_agent,
            debugger_agent=self.debugger_agent,
            reviewer_agent=self.reviewer_agent,
            documentation_agent=self.documentation_agent,
            materialization_service=self.materialization_service,
            testing_service=self.testing_service,
            knowledge_manager=self.knowledge_manager,
            static_validation_service=StaticValidationService(),
            documentation_prefetch_service=self.documentation_prefetch_service,
            repository_integrity_validator=self.repository_integrity_validator,
            test_discovery_service=self.test_discovery_service,
            environment_preflight_service=self.environment_preflight_service,
            dependency_preparation_service=self.dependency_preparation_service,
            repository_completeness_service=self.repository_completeness_service,
            event_dispatcher=self.event_dispatcher,
        )


        self.workflow = WorkflowBuilder(
            self.nodes
        )

        self.graph = self.workflow.build()

        self.db_engine = create_db_engine()
        self.db_session_factory = (
            session_factory_for(self.db_engine) if self.db_engine is not None else None
        )

        self.run_service = RunService(db_session_factory=self.db_session_factory)

        self.checkpoint_service = CheckpointService(db_session_factory=self.db_session_factory)

        self.db_sync_service = DatabaseSyncService(
            session_factory=self.db_session_factory,
            run_service=self.run_service,
            checkpoint_service=self.checkpoint_service,
        )
        self.event_dispatcher.subscribe(self.db_sync_service.handle_event)

        self.auth_service = AuthService()

        self.rate_limiter = RateLimiter()

        self.repository_service = RepositoryService(
            tool_registry=self.tool_registry,
            event_dispatcher=self.event_dispatcher,
            db_session_factory=self.db_session_factory,
            materialization_service=self.materialization_service,
        )

        logger.info("AgentForge application initialized")

    def graph_for_run(self, run_id: str, **compile_kwargs):

        checkpointer = self.checkpoint_service.checkpointer_for_run(run_id)

        return self.workflow.build(
            checkpointer=checkpointer,
            event_dispatcher=self.event_dispatcher,
            run_id=run_id,
            tracing_service=self.tracing_service,
            **compile_kwargs,
        )

    def start_project_run(
        self,
        *,
        project_id: str | None,
        request: str,
        owner_id: str | None = None,
        latest_run_id: str | None = None,
    ) -> tuple[str, str, WorkflowState]:

        if project_id is None:
            project_id = generate_project_id()

            if self.db_session_factory is not None:
                try:
                    with self.db_session_factory() as session:
                        ProjectRepository(session).create(
                            id=project_id,
                            user_id=uuid.UUID(owner_id) if owner_id else None,
                            name=request[:120],
                            initial_prompt=request,
                        )
                        session.commit()
                except Exception:
                    logger.warning(
                        "Failed to create project row for %s; continuing without it.",
                        project_id,
                        exc_info=True,
                    )

            state = WorkflowState()
            state.conversation.messages = [HumanMessage(content=request)]
        else:
            if latest_run_id is None:
                raise ValueError(
                    "latest_run_id is required to continue an existing project."
                )

            prior_state = self.run_service.load_state(latest_run_id)
            state = self.run_service.seed_continuation_state(prior_state, request)

        state.project.output_directory = str(WORKSPACE_ROOT / project_id)

        metadata = self.run_service.create_run(owner_id=owner_id, project_id=project_id)
        self.run_service.save_state(metadata.run_id, state)

        self.event_dispatcher.emit(
            WorkflowEvent(
                event_type=EventType.WORKFLOW_STARTED,
                run_id=metadata.run_id,
                metadata={"project_id": project_id},
            )
        )

        final_state = self._execute(metadata.run_id, state)

        return project_id, metadata.run_id, final_state

    def start_run(self, request: str, *, owner_id: str | None = None) -> tuple[str, WorkflowState]:
        _project_id, run_id, final_state = self.start_project_run(
            project_id=None, request=request, owner_id=owner_id
        )

        return run_id, final_state

    def resume_run(self, run_id: str) -> tuple[WorkflowState, bool]:

        current_state = self.run_service.load_state(run_id)

        if current_state.execution.workflow_status in (
            WorkflowStatus.COMPLETED,
            WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES,
            WorkflowStatus.FAILED,
        ):
            return current_state, True

        self.event_dispatcher.emit(
            WorkflowEvent(
                event_type=EventType.WORKFLOW_RESUMED,
                run_id=run_id,
            )
        )

        final_state = self._execute(run_id, None)

        return final_state, False

    def retry_failed_agent(self, run_id: str) -> WorkflowState:

        checkpoints = self.checkpoint_service.list_checkpoints(run_id)

        if not checkpoints:
            raise RunCorruptedError(
                f"No checkpoints found for run {run_id!r}.", details={"run_id": run_id}
            )

        return self.restart_from_checkpoint(run_id, checkpoints[0].checkpoint_id)

    def restart_from_checkpoint(self, run_id: str, checkpoint_id: str) -> WorkflowState:

        graph = self.graph_for_run(run_id)
        target_config = {
            "configurable": {
                "thread_id": run_id,
                "checkpoint_ns": "",
                "checkpoint_id": checkpoint_id,
            }
        }
        snapshot = graph.get_state(target_config)

        if not snapshot.values:
            raise RunCorruptedError(
                f"Checkpoint {checkpoint_id!r} not found for run {run_id!r}.",
                details={"run_id": run_id, "checkpoint_id": checkpoint_id},
            )

        checkpointed_state = WorkflowState.model_validate(snapshot.values)
        execution = checkpointed_state.execution
        as_node = execution.current_agent.value if execution.current_agent else None

        execution.workflow_status = WorkflowStatus.RUNNING
        execution.error_message = None
        execution.test_retry_count = 0
        execution.review_retry_count = 0
        execution.last_repair_trigger = RepairTrigger.NONE

        graph.update_state(target_config, {"execution": execution}, as_node=as_node)

        self.event_dispatcher.emit(
            WorkflowEvent(
                event_type=EventType.RECOVERY_ACTION_TAKEN,
                run_id=run_id,
                metadata={"mode": "restart_from_checkpoint", "checkpoint_id": checkpoint_id},
            )
        )
        self.event_dispatcher.emit(
            WorkflowEvent(event_type=EventType.WORKFLOW_RESUMED, run_id=run_id)
        )

        return self._execute(run_id, None)

    def restart_workflow(
        self, *, project_id: str, latest_run_id: str, owner_id: str | None = None
    ) -> tuple[str, str, WorkflowState]:

        prior_state = self.run_service.load_state(latest_run_id)
        self._backup_workspace(prior_state.project.output_directory, latest_run_id)

        state = self.run_service.seed_restart_state(prior_state)
        metadata = self.run_service.create_run(owner_id=owner_id, project_id=project_id)
        self.run_service.save_state(metadata.run_id, state)

        self.event_dispatcher.emit(
            WorkflowEvent(
                event_type=EventType.RECOVERY_ACTION_TAKEN,
                run_id=metadata.run_id,
                metadata={"mode": "restart_workflow", "source_run_id": latest_run_id},
            )
        )
        self.event_dispatcher.emit(
            WorkflowEvent(
                event_type=EventType.WORKFLOW_STARTED,
                run_id=metadata.run_id,
                metadata={"project_id": project_id},
            )
        )

        final_state = self._execute(metadata.run_id, state)

        return project_id, metadata.run_id, final_state

    def duplicate_and_retry(
        self, *, latest_run_id: str, owner_id: str | None = None
    ) -> tuple[str, str, WorkflowState]:

        prior_state = self.run_service.load_state(latest_run_id)
        original_message = (
            prior_state.conversation.messages[0].content if prior_state.conversation.messages else ""
        )

        self.event_dispatcher.emit(
            WorkflowEvent(
                event_type=EventType.RECOVERY_ACTION_TAKEN,
                run_id=latest_run_id,
                metadata={"mode": "duplicate_and_retry"},
            )
        )

        return self.start_project_run(
            project_id=None, request=str(original_message), owner_id=owner_id
        )

    @staticmethod
    def _backup_workspace(output_directory: str | None, run_id: str) -> None:

        if not output_directory:
            return

        source = Path(output_directory)

        if not source.exists():
            return

        backup_dir = source / ".backups" / run_id

        try:
            shutil.copytree(
                source,
                backup_dir,
                ignore=shutil.ignore_patterns(".backups"),
                dirs_exist_ok=True,
            )
        except Exception:
            logger.warning(
                "Failed to back up workspace at %s before restart; continuing anyway.",
                output_directory,
                exc_info=True,
            )

    def is_resuming(self, run_id: str) -> bool:
        with self._resume_lock:
            return run_id in self._resuming_runs

    def mark_resuming(self, run_id: str) -> None:
        with self._resume_lock:
            self._resuming_runs.add(run_id)

    def clear_resuming(self, run_id: str) -> None:
        with self._resume_lock:
            self._resuming_runs.discard(run_id)

    def _execute(
        self,
        run_id: str,
        state: WorkflowState | None,
    ) -> WorkflowState:

        graph = self.graph_for_run(run_id)
        config = {
            "configurable": {"thread_id": run_id},
            "recursion_limit": _INVOKE_RECURSION_LIMIT,
        }

        set_current_run_id(run_id)

        try:
            with self.tracing_service.trace(
                "workflow",
                run_type="chain",
                tags=[f"run_id:{run_id}"],
                metadata={"run_id": run_id},
            ) as workflow_run:
                try:
                    result = graph.invoke(state, config=config)
                except KeyboardInterrupt as error:
                    self.event_dispatcher.emit(
                        WorkflowEvent(
                            event_type=EventType.WORKFLOW_INTERRUPTED,
                            run_id=run_id,
                        )
                    )
                    error.run_id = run_id
                    raise
                except Exception as error:
                    self._persist_failure_state(run_id, config, error)

                    self.event_dispatcher.emit(
                        WorkflowEvent(
                            event_type=EventType.WORKFLOW_FAILED,
                            run_id=run_id,
                            message=str(error),
                        )
                    )
                    error.run_id = run_id
                    raise

                workflow_state = (
                    result
                    if isinstance(result, WorkflowState)
                    else WorkflowState.model_validate(result)
                )

                status = workflow_state.execution.workflow_status

                if status in (WorkflowStatus.COMPLETED, WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES):
                    workflow_state.conversation.messages = [
                        *workflow_state.conversation.messages,
                        AIMessage(content=_synthesize_assistant_reply(workflow_state)),
                    ]

                self.run_service.save_state(run_id, workflow_state)

                if self.failure_bundle_service.should_persist(workflow_state):
                    bundle = self.failure_bundle_service.build(run_id=run_id, state=workflow_state)
                    self.run_service.save_failure_bundle(run_id, bundle)

                self.tracing_service.set_outputs(
                    workflow_run, {"workflow_status": status.value}
                )

                if status == WorkflowStatus.COMPLETED:
                    self.event_dispatcher.emit(
                        WorkflowEvent(
                            event_type=EventType.WORKFLOW_COMPLETED,
                            run_id=run_id,
                        )
                    )
                elif status == WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES:
                    self.event_dispatcher.emit(
                        WorkflowEvent(
                            event_type=EventType.WORKFLOW_COMPLETED_WITH_VERIFICATION_ISSUES,
                            run_id=run_id,
                            message=workflow_state.execution.error_message,
                        )
                    )
                elif status == WorkflowStatus.FAILED:
                    self.event_dispatcher.emit(
                        WorkflowEvent(
                            event_type=EventType.WORKFLOW_FAILED,
                            run_id=run_id,
                            message=workflow_state.execution.error_message,
                        )
                    )
                else:
                    self.event_dispatcher.emit(
                        WorkflowEvent(
                            event_type=EventType.WORKFLOW_INTERRUPTED,
                            run_id=run_id,
                        )
                    )
        finally:
            set_current_run_id(None)

        return workflow_state

    def _persist_failure_state(
        self,
        run_id: str,
        config: dict[str, Any],
        error: Exception,
    ) -> None:

        try:
            graph = self.graph_for_run(run_id)
            snapshot = graph.get_state(config)

            workflow_state = (
                WorkflowState.model_validate(snapshot.values)
                if snapshot.values
                else self.run_service.load_state(run_id)
            )
        except Exception:
            logger.warning(
                "Could not recover checkpointed state for run %s after an "
                "uncaught node exception; run may remain stuck at its prior status.",
                run_id,
                exc_info=True,
            )
            return

        if workflow_state.execution.workflow_status in (
            WorkflowStatus.COMPLETED,
            WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES,
            WorkflowStatus.FAILED,
        ):
            return

        category = classify_exception(error)

        has_repository = bool(
            (workflow_state.repository_snapshot and workflow_state.repository_snapshot.file_tree)
            or workflow_state.implementation.written_files
        )

        workflow_state.execution.workflow_status = (
            WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES if has_repository else WorkflowStatus.FAILED
        )
        workflow_state.execution.error_message = (
            f"{workflow_state.execution.current_step or 'Workflow'} failed: {error}"
        )
        workflow_state.execution.completed_at = datetime.now(UTC)

        try:
            self.run_service.save_state(run_id, workflow_state)

            if self.failure_bundle_service.should_persist(workflow_state):
                bundle = self.failure_bundle_service.build(run_id=run_id, state=workflow_state)
                self.run_service.save_failure_bundle(run_id, bundle)

            logger.info(
                "Persisted FAILED status for run %s (classification=%s) after an uncaught node exception.",
                run_id,
                category.value,
            )
        except Exception:
            logger.warning(
                "Failed to persist FAILED status for run %s after an uncaught node exception.",
                run_id,
                exc_info=True,
            )

    def _register_tools(self) -> None:
        self.tool_registry.register(
            FilesystemTool(workspace=WORKSPACE_ROOT, tracing_service=self.tracing_service)
        )

        self.tool_registry.register(
            TerminalTool(workspace=WORKSPACE_ROOT, tracing_service=self.tracing_service)
        )

        self.tool_registry.register(
            GitTool(workspace=WORKSPACE_ROOT, tracing_service=self.tracing_service)
        )

        self.tool_registry.register(
            SearchTool(workspace=WORKSPACE_ROOT, tracing_service=self.tracing_service)
        )

    def _discover_mcp_tools(self) -> None:

        tools_by_server: dict[str, list] = {}

        for tool in load_tool_cache():
            tools_by_server.setdefault(tool.server_name, []).append(tool)

        for server_name in self.mcp_client_manager.enabled_server_names():
            self.mcp_tool_registry.register_server_tools(
                server_name, tools_by_server.get(server_name, [])
            )

    def shutdown(self) -> None:
        _run_async(self.mcp_client_manager.close_all())
        self.tracing_service.shutdown()

        if self.db_engine is not None:
            self.db_engine.dispose()

    async def ashutdown(self) -> None:

        await self.mcp_client_manager.close_all()
        self.tracing_service.shutdown()

        if self.db_engine is not None:
            self.db_engine.dispose()
