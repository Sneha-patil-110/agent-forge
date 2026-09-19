from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from backend.state.architecture_state import ArchitectureState
from backend.state.debug_state import DebugState
from backend.state.execution_state import AgentType, FailureCategory, WorkflowStatus
from backend.state.project_state import ProjectState
from backend.state.repository_snapshot import RepositorySnapshot
from backend.state.review_state import ReviewState
from backend.state.test_plan import TestPlan
from backend.state.tester_analysis import TesterAnalysis
from backend.state.testing_state import TestingState


class FailureBundle(BaseModel):

    run_id: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    workflow_status: WorkflowStatus
    failure_classification: FailureCategory | None = None
    error_message: str | None = None
    current_step: str | None = None
    current_agent: AgentType | None = None

    project: ProjectState
    architecture: ArchitectureState
    test_plans: list[TestPlan] = Field(default_factory=list)
    testing: TestingState
    tester_analysis: TesterAnalysis
    debug: DebugState
    review: ReviewState
    repair_history: list[dict] = Field(default_factory=list)
    repository_snapshot: RepositorySnapshot | None = None
    written_files: list[str] = Field(default_factory=list)

    test_retry_count: int
    review_retry_count: int

    state_file_reference: str = Field(
        default="state.json",
        description="Relative path (within the run directory) to the full WorkflowState for complete detail.",
    )
