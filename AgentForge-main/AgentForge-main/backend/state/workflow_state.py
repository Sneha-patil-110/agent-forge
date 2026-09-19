from __future__ import annotations

from pydantic import BaseModel, Field

from backend.state.architecture_state import ArchitectureState
from backend.state.conversation_state import ConversationState
from backend.state.debug_state import DebugState
from backend.state.documentation_state import DocumentationState
from backend.state.execution_state import ExecutionState
from backend.state.implementation_state import ImplementationState
from backend.state.knowledge_state import KnowledgeState
from backend.state.planning_state import PlanningState
from backend.state.project_state import ProjectState
from backend.state.repository_snapshot import RepositorySnapshot
from backend.state.research_state import ResearchState

from backend.state.review_state import ReviewState
from backend.state.test_plan import TestPlan
from backend.state.tester_analysis import TesterAnalysis
from backend.state.testing_state import TestingState


class WorkflowState(BaseModel):

    conversation: ConversationState = Field(
        default_factory=ConversationState,
    )

    project: ProjectState = Field(
        default_factory=ProjectState,
    )

    planning: PlanningState = Field(
        default_factory=PlanningState,
    )

    architecture: ArchitectureState = Field(
        default_factory=ArchitectureState,
    )

    implementation: ImplementationState = Field(
        default_factory=ImplementationState,
    )

    testing: TestingState = Field(
        default_factory=TestingState,
    )

    debug: DebugState = Field(
        default_factory=DebugState,
    )

    review: ReviewState = Field(
        default_factory=ReviewState,
    )

    documentation: DocumentationState = Field(
        default_factory=DocumentationState,
    )

    knowledge: KnowledgeState = Field(
        default_factory=KnowledgeState,
    )

    research: ResearchState = Field(
        default_factory=ResearchState,
    )

    execution: ExecutionState = Field(
        default_factory=ExecutionState,
    )

    repository_snapshot: RepositorySnapshot | None = Field(
        default=None,
    )

    test_plans: list[TestPlan] = Field(
        default_factory=list,
        description="Deterministic per-sub-project test plans from TestDiscoveryService.",
    )

    tester_analysis: TesterAnalysis = Field(
        default_factory=TesterAnalysis,
    )

