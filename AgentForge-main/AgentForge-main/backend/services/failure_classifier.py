from __future__ import annotations

import logging
from typing import NamedTuple

from backend.core.exceptions import (
    AgentForgeException,
    MCPError,
    MaterializationError,
    PathValidationError,
    ProviderUnavailableError,
    RateLimitExceededError,
    RepositoryIntegrityError,
    StaticValidationError,
)
from backend.state.execution_state import FailureCategory

logger = logging.getLogger(__name__)


class ClassificationResult(NamedTuple):
    category: FailureCategory
    is_transient: bool
    recommended_action: str
    summary: str


class FailureClassifier:

    def classify(
        self,
        error: Exception | str,
        *,
        stage: str | None = None,
    ) -> ClassificationResult:
        error_text = str(error)
        lower_text = error_text.lower()

        if isinstance(error, PathValidationError):
            return ClassificationResult(
                category=FailureCategory.PATH_VALIDATION_ERROR,
                is_transient=False,
                recommended_action="repair_artifacts",
                summary=f"Path validation failed: {error}",
            )

        if isinstance(error, MaterializationError):
            return ClassificationResult(
                category=FailureCategory.MATERIALIZATION_ERROR,
                is_transient=False,
                recommended_action="stop_pipeline",
                summary=f"Materialization error: {error}",
            )

        if isinstance(error, RepositoryIntegrityError):
            return ClassificationResult(
                category=FailureCategory.REPOSITORY_INTEGRITY_ERROR,
                is_transient=False,
                recommended_action="repair_artifacts",
                summary=f"Repository integrity error: {error}",
            )

        if isinstance(error, StaticValidationError):
            return ClassificationResult(
                category=FailureCategory.STATIC_VALIDATION_ERROR,
                is_transient=False,
                recommended_action="debug_code",
                summary=f"Static validation error: {error}",
            )

        if isinstance(error, (RateLimitExceededError, ProviderUnavailableError)) or any(
            token in lower_text for token in ("429", "503", "502", "rate limit", "overloaded")
        ):
            return ClassificationResult(
                category=FailureCategory.PROVIDER_ERROR,
                is_transient=True,
                recommended_action="retry_provider",
                summary=f"Transient LLM provider error: {error_text[:200]}",
            )

        if isinstance(error, MCPError) or "mcp" in lower_text:
            return ClassificationResult(
                category=FailureCategory.MCP_ERROR,
                is_transient=True,
                recommended_action="fallback_mcp",
                summary=f"MCP server interaction error: {error_text[:200]}",
            )

        if "test" in (stage or "").lower() or "tests failed" in lower_text:
            return ClassificationResult(
                category=FailureCategory.TEST_FAILURE,
                is_transient=False,
                recommended_action="debug_code",
                summary="Test failure encountered.",
            )

        return ClassificationResult(
            category=FailureCategory.LLM_GENERATION_ERROR,
            is_transient=False,
            recommended_action="repair_artifacts",
            summary=f"General error: {error_text[:200]}",
        )
