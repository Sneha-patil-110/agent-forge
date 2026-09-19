
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from backend.core.workspace import REPOSITORY_ROOT
from backend.services.run_service import RunService
from backend.state.execution_state import WorkflowStatus


def _run_worker(
    *,
    phase: str,
    runs_root: Path,
    run_id: str,
    counts_file: Path,
    output_directory: Path,
) -> str:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tests.support.cross_process_resume_worker",
            "--phase",
            phase,
            "--runs-root",
            str(runs_root),
            "--run-id",
            run_id,
            "--counts-file",
            str(counts_file),
            "--output-directory",
            str(output_directory),
        ],
        cwd=str(REPOSITORY_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, (
        f"Worker phase {phase!r} failed with exit code {result.returncode}.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )

    return result.stdout


def test_genuine_cross_process_resume(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    output_directory = tmp_path / "project"
    counts_file = tmp_path / "counts.json"

    run_service = RunService(runs_root=runs_root)
    metadata = run_service.create_run()
    run_id = metadata.run_id

    stdout_a = _run_worker(
        phase="a",
        runs_root=runs_root,
        run_id=run_id,
        counts_file=counts_file,
        output_directory=output_directory,
    )
    assert "PHASE_A_DONE" in stdout_a

    counts_after_a = json.loads(counts_file.read_text(encoding="utf-8"))
    assert counts_after_a.get("analysis") == 1
    assert counts_after_a.get("planner") == 1
    assert counts_after_a.get("architect") == 1
    assert "developer" not in counts_after_a
    assert "tester" not in counts_after_a
    assert "reviewer" not in counts_after_a
    assert "documentation" not in counts_after_a

    state_after_a = run_service.load_state(run_id)
    assert state_after_a.execution.workflow_status != WorkflowStatus.COMPLETED

    stdout_b = _run_worker(
        phase="b",
        runs_root=runs_root,
        run_id=run_id,
        counts_file=counts_file,
        output_directory=output_directory,
    )
    assert "PHASE_B_DONE" in stdout_b

    counts_after_b = json.loads(counts_file.read_text(encoding="utf-8"))

    assert counts_after_b["analysis"] == 1
    assert counts_after_b["planner"] == 1
    assert counts_after_b["architect"] == 1

    assert counts_after_b["developer"] == 1
    assert counts_after_b.get("tester", 0) == 0
    assert counts_after_b["reviewer"] == 1
    assert counts_after_b["documentation"] == 1

    final_state = run_service.load_state(run_id)
    assert final_state.execution.workflow_status == WorkflowStatus.COMPLETED
    assert final_state.testing.passed is True
    assert final_state.review.passed is True
    assert final_state.execution.test_retry_count == 0
    assert final_state.execution.review_retry_count == 0

    assert (output_directory / "calc.py").exists()
    assert (output_directory / "test_calc.py").exists()
