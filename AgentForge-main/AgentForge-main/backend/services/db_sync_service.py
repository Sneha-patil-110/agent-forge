
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session, sessionmaker

from backend.core.exceptions import InvalidRunIdError
from backend.events.event_types import EventType, WorkflowEvent
from backend.repositories.agent_invocation_repository import AgentInvocationRepository
from backend.repositories.documentation_repository import DocumentationRepository
from backend.repositories.event_repository import EventRepository
from backend.repositories.generated_project_repository import GeneratedProjectRepository
from backend.repositories.knowledge_repository import KnowledgeRepository
from backend.repositories.mcp_execution_repository import MCPExecutionRepository
from backend.repositories.project_repository import ProjectRepository
from backend.repositories.run_repository import RunRepository
from backend.services.checkpoint_service import CheckpointService
from backend.services.run_service import RunService
from backend.state.workflow_state import WorkflowState
from backend.utils.run_id import validate_run_id

logger = logging.getLogger(__name__)

_SNAPSHOT_EVENTS = frozenset(
    {
        EventType.WORKFLOW_STARTED,
        EventType.WORKFLOW_RESUMED,
        EventType.AGENT_COMPLETED,
        EventType.TESTING_PASSED,
        EventType.TESTING_FAILED,
        EventType.REVIEW_PASSED,
        EventType.REVIEW_FAILED,
        EventType.REVIEWER_AUTO_PASSED,
        EventType.WORKFLOW_COMPLETED,
        EventType.WORKFLOW_COMPLETED_WITH_VERIFICATION_ISSUES,
        EventType.WORKFLOW_FAILED,
        EventType.WORKFLOW_INTERRUPTED,
        EventType.DOCUMENTATION_GENERATED,
    }
)


def _latest_human_message(state: WorkflowState) -> str | None:

    if not state.conversation.messages:
        return None

    content = state.conversation.messages[-1].content

    if isinstance(content, str) and content.strip():
        return content.strip()[:2000]

    return None


class DatabaseSyncService:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session] | None,
        run_service: RunService,
        checkpoint_service: CheckpointService | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.run_service = run_service
        self.checkpoint_service = checkpoint_service

    @property
    def enabled(self) -> bool:
        return self.session_factory is not None

    def handle_event(self, event: WorkflowEvent) -> None:
        if self.session_factory is None or not event.run_id:
            return

        try:
            validate_run_id(event.run_id)
        except InvalidRunIdError:
            logger.warning("Ignoring event with an invalid run_id: %r", event.run_id)
            return

        try:
            sync_checkpoint = False
            with self.session_factory() as session:
                sync_checkpoint = (
                    event.event_type in _SNAPSHOT_EVENTS
                    or RunRepository(session).get(event.run_id) is None
                )

                if sync_checkpoint:
                    self._sync_snapshot(session, event.run_id)

                if event.event_type == EventType.AGENT_INVOCATION_RECORDED:
                    self._sync_agent_invocation(session, event)
                elif event.event_type == EventType.MCP_TOOL_CALL_RECORDED:
                    self._sync_mcp_execution(session, event)

                EventRepository(session).add(
                    run_id=event.run_id,
                    event_type=event.event_type.value,
                    agent=event.agent.value if event.agent else None,
                    message=event.message,
                    event_metadata=event.metadata,
                    timestamp=event.timestamp,
                )

                session.commit()

            if sync_checkpoint and self.checkpoint_service is not None:
                self.checkpoint_service.sync_to_db(event.run_id)

        except Exception:
            logger.warning(
                "Database sync failed for event %s on run %s; continuing without it.",
                event.event_type.value,
                event.run_id,
                exc_info=True,
            )

    def _sync_snapshot(self, session: Session, run_id: str) -> None:
        try:
            metadata = self.run_service.load_metadata(run_id)
            state = self.run_service.load_state(run_id)
            owner_id = uuid.UUID(metadata.owner_id) if metadata.owner_id else None
            project_id = metadata.project_id
            created_at = metadata.created_at
            updated_at = metadata.updated_at
            status = state.execution.workflow_status.value
            current_step = state.execution.current_step
            current_agent = state.execution.current_agent.value if state.execution.current_agent else None
            error_message = state.execution.error_message
            test_retry_count = state.execution.test_retry_count
            review_retry_count = state.execution.review_retry_count
            started_at = state.execution.started_at
            completed_at = state.execution.completed_at
            request_text = _latest_human_message(state)
            project_name = state.project.project_name
            project_description = state.project.project_description
            objective = state.project.objective
            project_status = state.project.status.value
            backend_tech = state.project.backend
            frontend_tech = state.project.frontend
            database_tech = state.project.database
            deployment_tech = state.project.deployment
            requirements = state.project.requirements
            tech_stack = state.project.tech_stack
            output_directory = state.project.output_directory
            knowledge_entries = state.knowledge.entries
            written_docs = set(state.documentation.written_files)
            failed_doc_paths = {error.split(":", 1)[0] for error in state.documentation.file_write_errors}
            generated_docs = state.documentation.generated_docs
        except Exception:
            owner_id = None
            project_id = None
            now = datetime.now(timezone.utc)
            created_at = now
            updated_at = now
            status = "running"
            current_step = None
            current_agent = None
            error_message = None
            test_retry_count = 0
            review_retry_count = 0
            started_at = None
            completed_at = None
            request_text = None
            project_name = "Generated Project"
            project_description = None
            objective = None
            project_status = "initialized"
            backend_tech = None
            frontend_tech = None
            database_tech = None
            deployment_tech = None
            requirements = []
            tech_stack = []
            output_directory = None
            knowledge_entries = []
            written_docs = set()
            failed_doc_paths = set()
            generated_docs = []

        RunRepository(session).upsert(
            run_id=run_id,
            user_id=owner_id,
            status=status,
            current_step=current_step,
            current_agent=current_agent,
            error_message=error_message,
            test_retry_count=test_retry_count,
            review_retry_count=review_retry_count,
            created_at=created_at,
            updated_at=updated_at,
            started_at=started_at,
            completed_at=completed_at,
            project_id=project_id,
            request_text=request_text,
        )

        if project_id is not None:
            ProjectRepository(session).attach_run(project_id, run_id)
            ProjectRepository(session).update_status(
                project_id, status
            )

        GeneratedProjectRepository(session).upsert(
            run_id=run_id,
            project_name=project_name,
            project_description=project_description,
            objective=objective,
            status=project_status,
            backend_tech=backend_tech,
            frontend_tech=frontend_tech,
            database_tech=database_tech,
            deployment_tech=deployment_tech,
            requirements=requirements,
            tech_stack=tech_stack,
            output_directory=output_directory,
        )

        knowledge_repo = KnowledgeRepository(session)

        for entry in knowledge_entries:
            knowledge_repo.upsert(
                run_id=run_id,
                entry_id=entry.id,
                category=entry.category.value,
                title=entry.title,
                content=entry.content,
                created_by=entry.created_by,
                status=entry.status.value,
                source_id=entry.source_id,
                supersedes=entry.supersedes,
                created_at=entry.created_at,
                updated_at=entry.updated_at,
            )

        documentation_repo = DocumentationRepository(session)

        for doc in generated_docs:
            if doc.path not in written_docs and doc.path not in failed_doc_paths:
                continue

            documentation_repo.upsert(
                run_id=run_id,
                path=doc.path,
                title=doc.title,
                description=doc.description,
                generating_agent="documentation",
                status="generated" if doc.path in written_docs else "failed",
            )

    def _sync_agent_invocation(self, session: Session, event: WorkflowEvent) -> None:
        metadata = event.metadata
        started_at_raw = metadata.get("started_at")

        AgentInvocationRepository(session).add(
            run_id=event.run_id,
            agent=event.agent.value if event.agent else "unknown",
            attempt_number=metadata.get("attempt_number") or 1,
            repair_trigger=metadata.get("repair_trigger"),
            status=metadata.get("status", "success"),
            provider=metadata.get("provider"),
            model=metadata.get("model"),
            provider_request_id=metadata.get("provider_request_id"),
            input_tokens=metadata.get("input_tokens"),
            output_tokens=metadata.get("output_tokens"),
            prompt_characters=metadata.get("prompt_characters"),
            response_characters=metadata.get("response_characters"),
            exception_type=metadata.get("exception_type"),
            failure_category=metadata.get("failure_category"),
            recovery_reason=metadata.get("recovery_reason"),
            error_message=metadata.get("error_message"),
            stacktrace=metadata.get("stacktrace"),
            checkpoint_id=metadata.get("checkpoint_id"),
            duration_ms=metadata.get("duration_ms"),
            started_at=datetime.fromisoformat(started_at_raw) if started_at_raw else event.timestamp,
            completed_at=event.timestamp,
        )

    def _sync_mcp_execution(self, session: Session, event: WorkflowEvent) -> None:
        metadata = event.metadata

        MCPExecutionRepository(session).add(
            run_id=event.run_id,
            agent=event.agent.value if event.agent else "unknown",
            server_name=metadata.get("server_name", "unknown"),
            tool_name=metadata.get("tool_name", "unknown"),
            success=bool(metadata.get("success")),
            duration_ms=metadata.get("duration_ms"),
            error_message=metadata.get("error_message"),
            occurred_at=event.timestamp,
        )