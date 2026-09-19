
from __future__ import annotations

import uuid

from langchain_core.messages import AIMessage, HumanMessage

from backend.events.dispatcher import EventDispatcher
from backend.events.event_types import EventType, WorkflowEvent
from backend.graph.builder import WorkflowBuilder
from backend.graph.nodes import WorkflowNodes
from backend.mcp.client_manager import MCPClientManager
from backend.mcp.registry import MCPToolRegistry
from backend.repositories.project_repository import ProjectRepository
from backend.services.auth_service import AuthService
from backend.services.checkpoint_service import CheckpointService
from backend.services.db_sync_service import DatabaseSyncService
from backend.services.mcp_management_service import MCPManagementService
from backend.services.rate_limiter import RateLimiter
from backend.services.repository_service import RepositoryService
from backend.services.run_service import RunService
from backend.state.execution_state import WorkflowStatus
from backend.tools.tool_registry import ToolRegistry
from backend.utils.project_id import generate_project_id


class _NoopAgent:
    def run(self, state):
        return state


class FakeApplication:
    def __init__(
        self,
        *,
        run_service: RunService,
        db_session_factory=None,
        auth_service: AuthService | None = None,
        start_status: WorkflowStatus = WorkflowStatus.COMPLETED,
    ) -> None:
        self.run_service = run_service
        self.event_dispatcher = EventDispatcher()
        self.db_session_factory = db_session_factory
        self.auth_service = auth_service or AuthService(
            secret="test-secret-key-at-least-32-bytes-long", algorithm="HS256"
        )
        self.rate_limiter = RateLimiter()
        self.tool_registry = ToolRegistry()
        self.repository_service = RepositoryService(
            tool_registry=self.tool_registry,
            event_dispatcher=self.event_dispatcher,
            db_session_factory=db_session_factory,
        )
        self.mcp_client_manager = MCPClientManager({})
        self.mcp_tool_registry = MCPToolRegistry()
        self.mcp_management_service = MCPManagementService(
            client_manager=self.mcp_client_manager,
            tool_registry=self.mcp_tool_registry,
        )
        self._start_status = start_status
        self.start_run_calls: list[str] = []
        self.resume_run_calls: list[str] = []
        self.retry_failed_agent_calls: list[str] = []
        self.restart_from_checkpoint_calls: list[tuple[str, str]] = []
        self.restart_workflow_calls: list[str] = []
        self.duplicate_and_retry_calls: list[str] = []
        self._resuming_runs: set[str] = set()
        self.checkpoint_service = CheckpointService(runs_root=run_service.runs_root)
        self.workflow = WorkflowBuilder(
            WorkflowNodes(
                analysis_agent=_NoopAgent(),
                planner_agent=_NoopAgent(),
                architect_agent=_NoopAgent(),
                developer_agent=_NoopAgent(),
                tester_agent=_NoopAgent(),
                debugger_agent=_NoopAgent(),
                reviewer_agent=_NoopAgent(),
                documentation_agent=_NoopAgent(),
                materialization_service=None,
                testing_service=None,
            )
        )

        self.db_sync_service = DatabaseSyncService(
            session_factory=db_session_factory,
            run_service=run_service,
        )
        self.event_dispatcher.subscribe(self.db_sync_service.handle_event)

    def start_run(self, request: str, *, owner_id: str | None = None):
        self.start_run_calls.append(request)
        metadata = self.run_service.create_run(owner_id=owner_id)

        self.event_dispatcher.emit(WorkflowEvent(event_type=EventType.WORKFLOW_STARTED, run_id=metadata.run_id))

        state = self.run_service.load_state(metadata.run_id)
        state.execution.workflow_status = self._start_status

        if self._start_status == WorkflowStatus.FAILED:
            state.execution.error_message = "Simulated failure."

        self.run_service.save_state(metadata.run_id, state)

        terminal_event = (
            EventType.WORKFLOW_COMPLETED
            if self._start_status == WorkflowStatus.COMPLETED
            else EventType.WORKFLOW_FAILED
        )
        self.event_dispatcher.emit(WorkflowEvent(event_type=terminal_event, run_id=metadata.run_id))

        return metadata.run_id, state

    def start_project_run(
        self,
        *,
        project_id: str | None,
        request: str,
        owner_id: str | None = None,
        latest_run_id: str | None = None,
    ):
        self.start_run_calls.append(request)

        if project_id is None:
            project_id = generate_project_id()

            if self.db_session_factory is not None:
                with self.db_session_factory() as session:
                    ProjectRepository(session).create(
                        id=project_id,
                        user_id=uuid.UUID(owner_id) if owner_id else None,
                        name=request[:120],
                        initial_prompt=request,
                    )
                    session.commit()

        metadata = self.run_service.create_run(owner_id=owner_id, project_id=project_id)

        if latest_run_id is not None:
            prior_state = self.run_service.load_state(latest_run_id)
            state = self.run_service.seed_continuation_state(prior_state, request)
        else:
            state = self.run_service.load_state(metadata.run_id)
            state.conversation.messages = [HumanMessage(content=request)]

        self.run_service.save_state(metadata.run_id, state)

        self.event_dispatcher.emit(
            WorkflowEvent(
                event_type=EventType.WORKFLOW_STARTED,
                run_id=metadata.run_id,
                metadata={"project_id": project_id},
            )
        )

        state.execution.workflow_status = self._start_status

        if self._start_status == WorkflowStatus.FAILED:
            state.execution.error_message = "Simulated failure."
        elif self._start_status == WorkflowStatus.COMPLETED:
            state.conversation.messages = [*state.conversation.messages, AIMessage(content="Done.")]

        self.run_service.save_state(metadata.run_id, state)

        terminal_event = (
            EventType.WORKFLOW_COMPLETED
            if self._start_status == WorkflowStatus.COMPLETED
            else EventType.WORKFLOW_FAILED
        )
        self.event_dispatcher.emit(WorkflowEvent(event_type=terminal_event, run_id=metadata.run_id))

        return project_id, metadata.run_id, state

    def resume_run(self, run_id: str):
        self.resume_run_calls.append(run_id)

        state = self.run_service.load_state(run_id)
        state.execution.workflow_status = WorkflowStatus.COMPLETED
        self.run_service.save_state(run_id, state)

        self.event_dispatcher.emit(WorkflowEvent(event_type=EventType.WORKFLOW_COMPLETED, run_id=run_id))

        return state, False

    def retry_failed_agent(self, run_id: str):
        self.retry_failed_agent_calls.append(run_id)

        state = self.run_service.load_state(run_id)
        state.execution.workflow_status = WorkflowStatus.COMPLETED
        self.run_service.save_state(run_id, state)

        self.event_dispatcher.emit(WorkflowEvent(event_type=EventType.WORKFLOW_COMPLETED, run_id=run_id))

        return state

    def restart_from_checkpoint(self, run_id: str, checkpoint_id: str):
        self.restart_from_checkpoint_calls.append((run_id, checkpoint_id))

        state = self.run_service.load_state(run_id)
        state.execution.workflow_status = WorkflowStatus.COMPLETED
        self.run_service.save_state(run_id, state)

        self.event_dispatcher.emit(WorkflowEvent(event_type=EventType.WORKFLOW_COMPLETED, run_id=run_id))

        return state

    def restart_workflow(self, *, project_id: str, latest_run_id: str, owner_id: str | None = None):
        self.restart_workflow_calls.append(latest_run_id)

        metadata = self.run_service.create_run(owner_id=owner_id, project_id=project_id)
        state = self.run_service.load_state(metadata.run_id)
        state.execution.workflow_status = self._start_status
        self.run_service.save_state(metadata.run_id, state)

        self.event_dispatcher.emit(
            WorkflowEvent(
                event_type=EventType.WORKFLOW_STARTED,
                run_id=metadata.run_id,
                metadata={"project_id": project_id},
            )
        )

        return project_id, metadata.run_id, state

    def duplicate_and_retry(self, *, latest_run_id: str, owner_id: str | None = None):
        self.duplicate_and_retry_calls.append(latest_run_id)

        prior_state = self.run_service.load_state(latest_run_id)
        original_message = (
            prior_state.conversation.messages[0].content if prior_state.conversation.messages else ""
        )

        return self.start_project_run(project_id=None, request=str(original_message), owner_id=owner_id)

    def is_resuming(self, run_id: str) -> bool:
        return run_id in self._resuming_runs

    def mark_resuming(self, run_id: str) -> None:
        self._resuming_runs.add(run_id)

    def clear_resuming(self, run_id: str) -> None:
        self._resuming_runs.discard(run_id)