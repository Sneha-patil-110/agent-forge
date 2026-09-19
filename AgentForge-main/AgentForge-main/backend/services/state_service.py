from __future__ import annotations

from copy import deepcopy

from backend.state.workflow_state import WorkflowState


class StateService:
    @staticmethod
    def create() -> WorkflowState:
        return WorkflowState()

    @staticmethod
    def clone(
        state: WorkflowState,
    ) -> WorkflowState:
        return deepcopy(state)

    @staticmethod
    def reset(
        state: WorkflowState,
    ) -> WorkflowState:
        return WorkflowState()

    @staticmethod
    def validate(
        state: WorkflowState,
    ) -> WorkflowState:
        return WorkflowState.model_validate(
            state.model_dump()
        )
