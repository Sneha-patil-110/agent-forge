
from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.agents.analysis_agent import AnalysisAgent
from backend.agents.architect_agent import ArchitectAgent
from backend.agents.debugger_agent import DebuggerAgent
from backend.agents.developer_agent import DeveloperAgent
from backend.agents.documenter_agent import DocumentationAgent
from backend.agents.planner_agent import PlannerAgent
from backend.agents.reviewer_agent import ReviewerAgent
from backend.agents.tester_agent import TesterAgent
from backend.graph.builder import WorkflowBuilder
from backend.graph.nodes import WorkflowNodes
from backend.graph.workflow import WorkflowNode
from backend.services.checkpoint_service import CheckpointService
from backend.services.materialization_service import MaterializationService
from backend.services.run_service import RunService
from backend.services.testing_service import TestingService
from backend.state.workflow_state import WorkflowState
from backend.tools.filesystem_tool import FilesystemTool
from backend.tools.terminal_tool import TerminalTool
from backend.tools.tool_registry import ToolRegistry

from tests.test_review_retry_integration import (
    REVIEW_PASSED,
    TEST_PLAN,
    VALID_ARCHITECTURE_STATE,
    VALID_DOCUMENTATION_STATE,
    VALID_PLANNING_STATE,
    VALID_PROJECT_STATE,
    WORKING_CALC_CONTENT,
    ScriptedLLMService,
    StubPromptService,
    _calc_file,
    _implementation_payload,
    _test_file,
)


def _bump_count(counts_path: Path, name: str) -> None:
    counts = json.loads(counts_path.read_text(encoding="utf-8")) if counts_path.exists() else {}
    counts[name] = counts.get(name, 0) + 1
    counts_path.write_text(json.dumps(counts), encoding="utf-8")


class _CountingAgent:

    def __init__(self, name: str, agent, counts_path: Path) -> None:
        self.name = name
        self.agent = agent
        self.counts_path = counts_path

    def run(self, state: WorkflowState) -> WorkflowState:
        _bump_count(self.counts_path, self.name)
        return self.agent.run(state)


def _build_builder(*, output_directory: Path, counts_path: Path) -> WorkflowBuilder:
    llm_service = ScriptedLLMService(
        {
            "analysis": [VALID_PROJECT_STATE],
            "planner": [VALID_PLANNING_STATE],
            "architect": [VALID_ARCHITECTURE_STATE],
            "developer": [
                _implementation_payload(
                    _calc_file(WORKING_CALC_CONTENT, "Calculator module."),
                    _test_file(),
                )
            ],
            "tester": [TEST_PLAN],
            "debugger": [],
            "reviewer": [REVIEW_PASSED],
            "documentation": [VALID_DOCUMENTATION_STATE],
        }
    )
    prompt_service = StubPromptService()

    def wrap(name: str, agent_cls):
        return _CountingAgent(name, agent_cls(prompt_service, llm_service), counts_path)

    tool_registry = ToolRegistry()
    tool_registry.register(FilesystemTool(workspace=output_directory))
    tool_registry.register(TerminalTool(workspace=output_directory))

    nodes = WorkflowNodes(
        analysis_agent=wrap("analysis", AnalysisAgent),
        planner_agent=wrap("planner", PlannerAgent),
        architect_agent=wrap("architect", ArchitectAgent),
        developer_agent=wrap("developer", DeveloperAgent),
        tester_agent=wrap("tester", TesterAgent),
        debugger_agent=wrap("debugger", DebuggerAgent),
        reviewer_agent=wrap("reviewer", ReviewerAgent),
        documentation_agent=wrap("documentation", DocumentationAgent),
        materialization_service=MaterializationService(tool_registry),
        testing_service=TestingService(tool_registry),
    )

    return WorkflowBuilder(nodes)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["a", "b"], required=True)
    parser.add_argument("--runs-root", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--counts-file", required=True)
    parser.add_argument("--output-directory", required=True)
    args = parser.parse_args()

    runs_root = Path(args.runs_root)
    counts_path = Path(args.counts_file)
    output_directory = Path(args.output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)

    run_service = RunService(runs_root=runs_root)
    checkpoint_service = CheckpointService(runs_root=runs_root)

    builder = _build_builder(output_directory=output_directory, counts_path=counts_path)
    checkpointer = checkpoint_service.checkpointer_for_run(args.run_id)
    config = {"configurable": {"thread_id": args.run_id}, "recursion_limit": 100}

    if args.phase == "a":
        graph = builder.build(
            checkpointer=checkpointer,
            interrupt_after=[WorkflowNode.ARCHITECT.value],
        )
        initial_state = run_service.load_state(args.run_id)
        initial_state.project.output_directory = str(output_directory)
        result = graph.invoke(initial_state, config=config)
    else:
        graph = builder.build(checkpointer=checkpointer)
        result = graph.invoke(None, config=config)

    state = (
        result
        if isinstance(result, WorkflowState)
        else WorkflowState.model_validate(result)
    )
    run_service.save_state(args.run_id, state)

    print(f"PHASE_{args.phase.upper()}_DONE status={state.execution.workflow_status.value}")


if __name__ == "__main__":
    main()
