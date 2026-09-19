from __future__ import annotations

from backend.core.app import Application
from backend.graph.builder import WorkflowBuilder
from backend.services.tracing_service import TracingService


def test_application_owns_a_single_tracing_service_shared_by_llm_service() -> None:
    application = Application()

    assert isinstance(application.tracing_service, TracingService)
    assert application.llm_service.tracing_service is application.tracing_service

    application.shutdown()


def test_graph_for_run_passes_the_shared_tracing_service_to_the_builder(
    monkeypatch, tmp_path
) -> None:
    from backend.services.checkpoint_service import CheckpointService
    from backend.services.run_service import RunService

    application = Application()
    application.run_service = RunService(runs_root=tmp_path / "runs")
    application.checkpoint_service = CheckpointService(runs_root=tmp_path / "runs")

    captured = {}
    original_build = WorkflowBuilder.build

    def _spy_build(self, **kwargs):
        captured.update(kwargs)
        return original_build(self, **kwargs)

    monkeypatch.setattr(WorkflowBuilder, "build", _spy_build)

    metadata = application.run_service.create_run()
    application.graph_for_run(metadata.run_id)

    assert captured["tracing_service"] is application.tracing_service

    application.shutdown()


def test_shutdown_calls_tracing_service_shutdown_and_is_idempotent(monkeypatch) -> None:
    application = Application()

    calls = []
    monkeypatch.setattr(
        application.tracing_service, "shutdown", lambda: calls.append(1)
    )

    application.shutdown()
    application.shutdown()

    assert calls == [1, 1]