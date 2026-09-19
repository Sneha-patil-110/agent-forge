from __future__ import annotations

from pathlib import Path

from langgraph.graph.state import CompiledStateGraph

from backend.core.app import Application
from backend.services.checkpoint_service import CheckpointService
from backend.services.run_service import RunService


def test_application_exposes_run_and_checkpoint_services() -> None:
    application = Application()

    assert isinstance(application.run_service, RunService)
    assert isinstance(application.checkpoint_service, CheckpointService)


def test_application_default_graph_is_unchanged_and_uncheckpointed() -> None:

    application = Application()

    assert isinstance(application.graph, CompiledStateGraph)
    assert application.graph.checkpointer is None


def test_graph_for_run_returns_checkpointed_graph_with_same_topology(
    tmp_path: Path,
) -> None:
    application = Application()
    application.run_service = RunService(runs_root=tmp_path / "runs")
    application.checkpoint_service = CheckpointService(runs_root=tmp_path / "runs")

    metadata = application.run_service.create_run()

    checkpointed_graph = application.graph_for_run(metadata.run_id)

    assert checkpointed_graph.checkpointer is not None
    assert sorted(checkpointed_graph.get_graph().nodes.keys()) == sorted(
        application.graph.get_graph().nodes.keys()
    )


def test_graph_for_run_uses_runs_root_scoped_checkpoint_file(tmp_path: Path) -> None:
    application = Application()
    application.run_service = RunService(runs_root=tmp_path / "runs")
    application.checkpoint_service = CheckpointService(runs_root=tmp_path / "runs")

    metadata = application.run_service.create_run()
    application.graph_for_run(metadata.run_id)

    db_path = tmp_path / "runs" / metadata.run_id / "checkpoints.sqlite"
    assert db_path.exists()
