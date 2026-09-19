
from __future__ import annotations

from pathlib import Path

from langchain_core.messages import HumanMessage

from backend.services.run_service import RunService
from backend.state.execution_state import WorkflowStatus
from backend.state.workflow_state import WorkflowState

from tests.test_review_retry_integration import (
    REVIEW_PASSED,
    TEST_PLAN,
    VALID_DOCUMENTATION_STATE,
    WORKING_CALC_CONTENT,
    _as_workflow_state,
    _build_workflow,
    _calc_file,
    _implementation_payload,
    _test_file,
)

MULTIPLY_CONTENT = "def multiply(a, b):\n    return a * b\n"


def _multiply_file() -> dict:
    return {
        "path": "multiply.py",
        "content": MULTIPLY_CONTENT,
        "language": "python",
        "description": "Multiplication helper.",
    }


def test_a_follow_up_run_additively_materializes_into_the_same_directory(
    tmp_path: Path,
) -> None:
    output_directory = tmp_path / "project"
    output_directory.mkdir()
    run_service = RunService(runs_root=tmp_path / "runs")

    graph, _llm_service = _build_workflow(
        developer_script=[
            _implementation_payload(
                _calc_file(WORKING_CALC_CONTENT, "Calculator module."),
                _test_file(),
            )
        ],
        tester_script=[TEST_PLAN],
        reviewer_script=[REVIEW_PASSED],
        debugger_script=[{}],
        output_directory=output_directory,
    )

    initial = WorkflowState()
    initial.project.output_directory = str(output_directory)
    initial.conversation.messages = [HumanMessage(content="Build a calculator CLI")]

    first_result = _as_workflow_state(graph.invoke(initial))

    assert first_result.execution.workflow_status == WorkflowStatus.COMPLETED
    assert set(first_result.implementation.written_files) == {"calc.py", "test_calc.py"}
    assert (output_directory / "calc.py").exists()
    assert (output_directory / "test_calc.py").exists()

    seeded = run_service.seed_continuation_state(first_result, "Add a multiply function")

    assert [m.content for m in seeded.conversation.messages] == [
        "Build a calculator CLI",
        "Add a multiply function",
    ]

    graph2, llm_service_2 = _build_workflow(
        developer_script=[_implementation_payload(_multiply_file())],
        tester_script=[TEST_PLAN],
        reviewer_script=[REVIEW_PASSED],
        debugger_script=[{}],
        output_directory=output_directory,
    )

    second_result = _as_workflow_state(graph2.invoke(seeded))

    assert second_result.execution.workflow_status == WorkflowStatus.COMPLETED

    assert set(second_result.implementation.written_files) == {
        "calc.py",
        "test_calc.py",
        "multiply.py",
    }
    assert (output_directory / "calc.py").read_text(encoding="utf-8") == WORKING_CALC_CONTENT
    assert (output_directory / "test_calc.py").exists()
    assert (output_directory / "multiply.py").read_text(encoding="utf-8") == MULTIPLY_CONTENT

    assert second_result.execution.test_retry_count == 0
    assert second_result.execution.review_retry_count == 0
    assert llm_service_2.call_count("developer") == 1
