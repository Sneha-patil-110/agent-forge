from __future__ import annotations

import time
import pytest

from backend.mcp.mcp_loop_runner import MCPLoopRunner
from backend.services.artifact_diff import compute_artifact_diff
from backend.services.context_manager import ContextManager
from backend.services.failure_fingerprint import compute_failure_fingerprint
from backend.services.testing_service import TestingService
from backend.state.implementation_state import GeneratedCode
from backend.state.testing_state import TestFailure, TestingState, TestStatus
from backend.state.workflow_state import WorkflowState


def test_mcp_loop_runner_execution_latency() -> None:
    runner = MCPLoopRunner.get_instance()

    async def sample_coro():
        return "fast_result"

    start = time.perf_counter()
    res1 = runner.run_coro(sample_coro(), timeout=5.0)
    dur1 = (time.perf_counter() - start) * 1000

    start = time.perf_counter()
    res2 = runner.run_coro(sample_coro(), timeout=5.0)
    dur2 = (time.perf_counter() - start) * 1000

    assert res1 == "fast_result"
    assert res2 == "fast_result"
    assert dur1 < 100.0
    assert dur2 < 100.0


def test_structured_test_failure_traceback_parsing() -> None:
    pytest_stdout = """
============================= FAILURES =============================
_________________________ test_user_login __________________________

    def test_user_login():
>       assert response.status_code == 200
E       AssertionError: assert 422 == 200

tests/test_auth.py:45: AssertionError
=========================== short test summary info ===========================
FAILED tests/test_auth.py::test_user_login - AssertionError: assert 422 == 200
======================== 1 failed in 0.12s =========================
"""
    failures = TestingService._parse_failed_tests(pytest_stdout)
    assert len(failures) == 1
    failure = failures[0]
    assert failure.name == "tests/test_auth.py::test_user_login"
    assert failure.file_path == "tests/test_auth.py"
    assert "AssertionError: assert 422 == 200" in (failure.message or "")
    assert failure.traceback is not None
    assert "AssertionError: assert 422 == 200" in failure.traceback


def test_artifact_diff_no_effect_detection() -> None:
    before = [
        GeneratedCode(path="backend/main.py", content="print('hello')", language="python"),
        GeneratedCode(path="frontend/src/App.tsx", content="export default App;", language="typescript"),
    ]
    after_identical = [
        GeneratedCode(path="backend/main.py", content="print('hello')", language="python"),
        GeneratedCode(path="frontend/src/App.tsx", content="export default App;", language="typescript"),
    ]
    diff_identical = compute_artifact_diff(before, after_identical)
    assert diff_identical.is_no_effect
    assert diff_identical.modified_files == []

    after_modified = [
        GeneratedCode(path="backend/main.py", content="print('hello world')", language="python"),
        GeneratedCode(path="frontend/src/App.tsx", content="export default App;", language="typescript"),
    ]
    diff_modified = compute_artifact_diff(before, after_modified)
    assert not diff_modified.is_no_effect
    assert diff_modified.modified_files == ["backend/main.py"]


def test_failure_fingerprint_deterministic_hashing() -> None:
    state1 = TestingState(
        status=TestStatus.FAILED,
        failed_tests=[
            TestFailure(
                name="tests/test_auth.py::test_login",
                message="AssertionError: assert 422 == 200",
                file_path="tests/test_auth.py",
                traceback="Traceback at line 45 in /tmp/run1/test_auth.py",
            )
        ],
    )
    state2 = TestingState(
        status=TestStatus.FAILED,
        failed_tests=[
            TestFailure(
                name="tests/test_auth.py::test_login",
                message="AssertionError: assert 422 == 200",
                file_path="tests/test_auth.py",
                traceback="Traceback at line 99 in /tmp/run2/test_auth.py",
            )
        ],
    )

    fp1 = compute_failure_fingerprint(state1)
    fp2 = compute_failure_fingerprint(state2)

    assert fp1 == fp2
    assert len(fp1) == 16


def test_build_targeted_command() -> None:
    full_cmd = ["pytest"]
    targeted = TestingService.build_targeted_command(full_cmd, ["tests/test_auth.py::test_login"])
    assert targeted == ["pytest", "tests/test_auth.py::test_login"]

    py_cmd = ["python", "-m", "pytest"]
    py_targeted = TestingService.build_targeted_command(py_cmd, ["tests/test_auth.py::test_login"])
    assert py_targeted == ["python", "-m", "pytest", "tests/test_auth.py::test_login"]


def test_tester_context_includes_real_test_execution_evidence() -> None:
    context_manager = ContextManager()
    state = WorkflowState()
    state.project.output_directory = "workspace/proj_test"
    state.implementation.written_files = ["backend/main.py"]
    state.testing.stdout = "FAILED test_main.py::test_health_check"

    rendered = context_manager.build_context(agent_name="tester", state=state)
    assert "Test Execution Evidence" in rendered
    assert "test_health_check" in rendered
