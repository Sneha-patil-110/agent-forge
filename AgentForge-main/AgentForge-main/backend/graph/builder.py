from __future__ import annotations

import time
import traceback
from datetime import UTC, datetime
from typing import Any, Callable

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from backend.core.failure_classification import classify_exception, to_recovery_reason
from backend.core.run_context import drain_llm_calls, reset_llm_calls
from backend.events.dispatcher import EventDispatcher
from backend.events.event_types import EventType, WorkflowEvent
from backend.graph.edges import WORKFLOW_EDGES
from backend.graph.nodes import WorkflowNodes
from backend.graph.router import WorkflowRouter
from backend.graph.workflow import WorkflowNode
from backend.services.tracing_service import TracingService
from backend.state.execution_state import AgentType, RepairTrigger
from backend.state.workflow_state import WorkflowState

NodeFn = Callable[[WorkflowState], WorkflowState]


class WorkflowBuilder:
    def __init__(
        self,
        nodes: WorkflowNodes,
    ) -> None:
        self.nodes = nodes

    def build(
        self,
        *,
        checkpointer: BaseCheckpointSaver | None = None,
        event_dispatcher: EventDispatcher | None = None,
        run_id: str | None = None,
        tracing_service: TracingService | None = None,
        **compile_kwargs: Any,
    ):
        graph = StateGraph(WorkflowState)

        def node(name: str, fn: NodeFn) -> NodeFn:
            wrapped = fn

            if tracing_service is not None:
                wrapped = self._wrap_with_tracing(
                    name=name,
                    fn=wrapped,
                    tracing_service=tracing_service,
                )

            if event_dispatcher is not None:
                wrapped = self._wrap_with_events(
                    name=name,
                    fn=wrapped,
                    event_dispatcher=event_dispatcher,
                    run_id=run_id,
                    checkpointer=checkpointer,
                )

            return wrapped

        graph.add_node(
            WorkflowNode.ANALYSIS.value,
            node(WorkflowNode.ANALYSIS.value, self.nodes.analysis),
        )

        graph.add_node(
            WorkflowNode.PLANNER.value,
            node(WorkflowNode.PLANNER.value, self.nodes.planner),
        )

        graph.add_node(
            WorkflowNode.ARCHITECT.value,
            node(WorkflowNode.ARCHITECT.value, self.nodes.architect),
        )

        graph.add_node(
            WorkflowNode.DEVELOPER.value,
            node(WorkflowNode.DEVELOPER.value, self.nodes.developer),
        )

        graph.add_node(
            WorkflowNode.STATIC_VALIDATION.value,
            node(WorkflowNode.STATIC_VALIDATION.value, self.nodes.static_validation),
        )

        graph.add_node(
            WorkflowNode.TESTER.value,
            node(WorkflowNode.TESTER.value, self.nodes.tester),
        )

        graph.add_node(
            WorkflowNode.DEBUGGER.value,
            node(WorkflowNode.DEBUGGER.value, self.nodes.debugger),
        )

        graph.add_node(
            WorkflowNode.REVIEWER.value,
            node(WorkflowNode.REVIEWER.value, self.nodes.reviewer),
        )

        graph.add_node(
            WorkflowNode.DOCUMENTATION.value,
            node(WorkflowNode.DOCUMENTATION.value, self.nodes.documentation),
        )

        graph.add_edge(
            START,
            WorkflowNode.ANALYSIS.value,
        )

        for source, target in WORKFLOW_EDGES:
            graph.add_edge(
                source.value,
                target.value,
            )

        graph.add_conditional_edges(
            WorkflowNode.STATIC_VALIDATION.value,
            WorkflowRouter.static_validation_router,
            {
                WorkflowNode.TESTER.value: WorkflowNode.TESTER.value,
                WorkflowNode.DEBUGGER.value: WorkflowNode.DEBUGGER.value,
                END: END,
            },
        )

        graph.add_conditional_edges(
            WorkflowNode.TESTER.value,
            WorkflowRouter.tester_router,
            {
                WorkflowNode.REVIEWER.value: WorkflowNode.REVIEWER.value,
                WorkflowNode.DEBUGGER.value: WorkflowNode.DEBUGGER.value,
                END: END,
            },
        )

        graph.add_conditional_edges(
            WorkflowNode.REVIEWER.value,
            WorkflowRouter.review_router,
            {
                WorkflowNode.DOCUMENTATION.value: WorkflowNode.DOCUMENTATION.value,
                WorkflowNode.DEBUGGER.value: WorkflowNode.DEBUGGER.value,
                END: END,
            },
        )

        graph.add_edge(
            WorkflowNode.DOCUMENTATION.value,
            END,
        )

        return graph.compile(checkpointer=checkpointer, **compile_kwargs)

    @staticmethod
    def _wrap_with_tracing(
        *,
        name: str,
        fn: NodeFn,
        tracing_service: TracingService,
    ) -> NodeFn:
        def wrapped(state: WorkflowState) -> WorkflowState:
            span_name, retry_metadata = WorkflowBuilder._retry_metadata(name, state)

            with tracing_service.trace(
                span_name,
                run_type="chain",
                tags=[f"agent:{name}"],
                metadata={"agent": name, "stage": span_name, **retry_metadata},
            ) as run:
                started_at = time.perf_counter()

                result = fn(state)

                tracing_service.set_outputs(
                    run,
                    {
                        "current_step": result.execution.current_step,
                        "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
                    },
                )

                return result

        return wrapped

    @staticmethod
    def _retry_metadata(name: str, state: WorkflowState) -> tuple[str, dict[str, Any]]:

        execution = state.execution

        if (
            name == WorkflowNode.DEVELOPER.value
            and execution.last_repair_trigger != RepairTrigger.NONE
        ):
            is_test_repair = execution.last_repair_trigger in (
                RepairTrigger.TEST_FAILURE,
                RepairTrigger.STATIC_VALIDATION_FAILURE,
            )

            return "developer_repair", {
                "retry_triggered_by": execution.last_repair_trigger.value,
                "retry_number": (
                    execution.test_retry_count
                    if is_test_repair
                    else execution.review_retry_count
                ),
                "previous_stage": (
                    WorkflowNode.TESTER.value if is_test_repair else WorkflowNode.REVIEWER.value
                ),
                "next_stage": WorkflowNode.TESTER.value,
            }

        if name == WorkflowNode.STATIC_VALIDATION.value:
            return name, {
                "attempt_number": execution.test_retry_count + 1,
                "previous_stage": WorkflowNode.DEVELOPER.value,
                "next_stage": WorkflowNode.TESTER.value,
            }

        if name == WorkflowNode.TESTER.value:
            return name, {
                "attempt_number": execution.test_retry_count + 1,
                "previous_stage": WorkflowNode.STATIC_VALIDATION.value,
                "next_stage": WorkflowNode.REVIEWER.value,
            }

        if name == WorkflowNode.DEBUGGER.value:
            if execution.last_repair_trigger == RepairTrigger.STATIC_VALIDATION_FAILURE:
                trigger, previous_stage = RepairTrigger.STATIC_VALIDATION_FAILURE, WorkflowNode.STATIC_VALIDATION
            elif execution.last_repair_trigger == RepairTrigger.REVIEW_FEEDBACK:
                trigger, previous_stage = RepairTrigger.REVIEW_FEEDBACK, WorkflowNode.REVIEWER
            else:
                trigger, previous_stage = RepairTrigger.TEST_FAILURE, WorkflowNode.TESTER

            return name, {
                "retry_triggered_by": trigger.value,
                "previous_stage": previous_stage.value,
                "next_stage": WorkflowNode.DEVELOPER.value,
            }

        if name == WorkflowNode.REVIEWER.value:
            return name, {
                "attempt_number": execution.review_retry_count + 1,
                "previous_stage": WorkflowNode.DEVELOPER.value,
                "next_stage": WorkflowNode.DOCUMENTATION.value,
            }

        return name, {}

    @staticmethod
    def _wrap_with_events(
        *,
        name: str,
        fn: NodeFn,
        event_dispatcher: EventDispatcher,
        run_id: str | None,
        checkpointer: BaseCheckpointSaver | None = None,
    ) -> NodeFn:
        agent = AgentType(name)

        def wrapped(state: WorkflowState) -> WorkflowState:
            event_dispatcher.emit(
                WorkflowEvent(
                    event_type=EventType.AGENT_STARTED,
                    run_id=run_id,
                    agent=agent,
                )
            )

            _, retry_metadata = WorkflowBuilder._retry_metadata(name, state)
            attempt_number = (
                retry_metadata.get("attempt_number") or retry_metadata.get("retry_number") or 1
            )
            repair_trigger = (
                state.execution.last_repair_trigger.value
                if state.execution.last_repair_trigger != RepairTrigger.NONE
                else None
            )

            reset_llm_calls()
            started_at = datetime.now(UTC)
            perf_started = time.perf_counter()

            try:
                result = fn(state)
            except Exception as error:
                duration_ms = round((time.perf_counter() - perf_started) * 1000)
                category = classify_exception(error)
                reason = to_recovery_reason(category=category)

                event_dispatcher.emit(
                    WorkflowEvent(
                        event_type=EventType.AGENT_INVOCATION_RECORDED,
                        run_id=run_id,
                        agent=agent,
                        metadata=WorkflowBuilder._invocation_metadata(
                            status="failure",
                            attempt_number=attempt_number,
                            repair_trigger=repair_trigger,
                            started_at=started_at,
                            duration_ms=duration_ms,
                            exception_type=f"{type(error).__module__}.{type(error).__qualname__}",
                            failure_category=category.value,
                            recovery_reason=reason.value,
                            error_message=str(error),
                            stacktrace=traceback.format_exc(),
                            checkpoint_id=WorkflowBuilder._latest_checkpoint_id(checkpointer, run_id),
                        ),
                    )
                )
                raise

            duration_ms = round((time.perf_counter() - perf_started) * 1000)

            testing_failed = (
                name in (WorkflowNode.TESTER.value, WorkflowNode.STATIC_VALIDATION.value)
                and not result.testing.passed
            )
            review_failed = name == WorkflowNode.REVIEWER.value and not result.review.passed
            invocation_failed = testing_failed or review_failed
            reason = (
                to_recovery_reason(
                    category=None, testing_failed=testing_failed, review_failed=review_failed
                )
                if invocation_failed
                else None
            )

            event_dispatcher.emit(
                WorkflowEvent(
                    event_type=EventType.AGENT_INVOCATION_RECORDED,
                    run_id=run_id,
                    agent=agent,
                    metadata=WorkflowBuilder._invocation_metadata(
                        status="failure" if invocation_failed else "success",
                        attempt_number=attempt_number,
                        repair_trigger=repair_trigger,
                        started_at=started_at,
                        duration_ms=duration_ms,
                        recovery_reason=reason.value if reason is not None else None,
                    ),
                )
            )

            event_dispatcher.emit(
                WorkflowEvent(
                    event_type=EventType.AGENT_COMPLETED,
                    run_id=run_id,
                    agent=agent,
                )
            )

            if name == WorkflowNode.TESTER.value:
                event_dispatcher.emit(
                    WorkflowEvent(
                        event_type=(
                            EventType.TESTING_PASSED
                            if result.testing.passed
                            else EventType.TESTING_FAILED
                        ),
                        run_id=run_id,
                        agent=agent,
                        metadata={"attempt_number": result.testing.attempt_number},
                    )
                )
            elif name == WorkflowNode.REVIEWER.value:
                event_dispatcher.emit(
                    WorkflowEvent(
                        event_type=(
                            EventType.REVIEW_PASSED
                            if result.review.passed
                            else EventType.REVIEW_FAILED
                        ),
                        run_id=run_id,
                        agent=agent,
                        metadata={"score": result.review.score},
                    )
                )
            elif name == WorkflowNode.DOCUMENTATION.value:
                event_dispatcher.emit(
                    WorkflowEvent(
                        event_type=EventType.DOCUMENTATION_GENERATED,
                        run_id=run_id,
                        agent=agent,
                        metadata={"file_count": len(result.documentation.written_files)},
                    )
                )

            return result

        return wrapped

    @staticmethod
    def _invocation_metadata(
        *,
        status: str,
        attempt_number: int,
        repair_trigger: str | None,
        started_at: datetime,
        duration_ms: int,
        exception_type: str | None = None,
        failure_category: str | None = None,
        recovery_reason: str | None = None,
        error_message: str | None = None,
        stacktrace: str | None = None,
        checkpoint_id: str | None = None,
    ) -> dict[str, Any]:
        calls = drain_llm_calls()
        input_tokens = [call.input_tokens for call in calls if call.input_tokens is not None]
        output_tokens = [call.output_tokens for call in calls if call.output_tokens is not None]

        return {
            "status": status,
            "attempt_number": attempt_number,
            "repair_trigger": repair_trigger,
            "provider": calls[0].provider if calls else None,
            "model": calls[0].model if calls else None,
            "provider_request_id": calls[-1].provider_request_id if calls else None,
            "input_tokens": sum(input_tokens) if input_tokens else None,
            "output_tokens": sum(output_tokens) if output_tokens else None,
            "prompt_characters": sum(call.prompt_characters for call in calls) if calls else None,
            "response_characters": sum(call.response_characters for call in calls) if calls else None,
            "exception_type": exception_type,
            "failure_category": failure_category,
            "recovery_reason": recovery_reason,
            "error_message": error_message[:4000] if error_message else None,
            "stacktrace": stacktrace[:8000] if stacktrace else None,
            "checkpoint_id": checkpoint_id,
            "duration_ms": duration_ms,
            "started_at": started_at.isoformat(),
        }

    @staticmethod
    def _latest_checkpoint_id(
        checkpointer: BaseCheckpointSaver | None, run_id: str | None
    ) -> str | None:

        if checkpointer is None or run_id is None:
            return None

        try:
            config = {"configurable": {"thread_id": run_id}}

            for checkpoint_tuple in checkpointer.list(config, limit=1):
                return checkpoint_tuple.config.get("configurable", {}).get("checkpoint_id")
        except Exception:
            return None

        return None
