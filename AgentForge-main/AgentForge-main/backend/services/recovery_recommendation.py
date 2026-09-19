from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

from backend.core.failure_classification import RecoveryReason


class RecoveryMode(str, Enum):
    RESUME = "resume"
    RETRY_AGENT = "retry_agent"
    RESTART_FROM_CHECKPOINT = "restart_from_checkpoint"
    RESTART_WORKFLOW = "restart_workflow"
    DUPLICATE_AND_RETRY = "duplicate_and_retry"


class RecoveryRecommendation(BaseModel):
    mode: RecoveryMode
    confidence: float
    explanation: str


_BASELINE: dict[RecoveryReason, RecoveryRecommendation] = {
    RecoveryReason.RATE_LIMIT: RecoveryRecommendation(
        mode=RecoveryMode.RETRY_AGENT,
        confidence=0.9,
        explanation="Provider rate limit -- usually resolved by retrying the same agent.",
    ),
    RecoveryReason.NETWORK_TIMEOUT: RecoveryRecommendation(
        mode=RecoveryMode.RETRY_AGENT,
        confidence=0.85,
        explanation="Network or timeout error -- typically transient.",
    ),
    RecoveryReason.DATABASE_ERROR: RecoveryRecommendation(
        mode=RecoveryMode.RETRY_AGENT,
        confidence=0.7,
        explanation="Database error -- often transient, but worth investigating if it recurs.",
    ),
    RecoveryReason.LLM_PARSE_ERROR: RecoveryRecommendation(
        mode=RecoveryMode.DUPLICATE_AND_RETRY,
        confidence=0.4,
        explanation=(
            "The model produced output AgentForge couldn't parse -- unlikely "
            "to differ on a bare retry; a fresh attempt gives it a clean run."
        ),
    ),
    RecoveryReason.INVALID_JSON: RecoveryRecommendation(
        mode=RecoveryMode.DUPLICATE_AND_RETRY,
        confidence=0.4,
        explanation="The model's structured output failed validation -- same reasoning as a parse error.",
    ),
    RecoveryReason.PYTEST_FAILURE: RecoveryRecommendation(
        mode=RecoveryMode.RETRY_AGENT,
        confidence=0.6,
        explanation="A real test failure -- retrying lets Debugger see the failure and try a different fix.",
    ),
    RecoveryReason.REVIEW_FAILURE: RecoveryRecommendation(
        mode=RecoveryMode.RETRY_AGENT,
        confidence=0.6,
        explanation="Review feedback -- retrying lets Developer address the reported issues.",
    ),
    RecoveryReason.WORKSPACE_ERROR: RecoveryRecommendation(
        mode=RecoveryMode.RESTART_FROM_CHECKPOINT,
        confidence=0.55,
        explanation=(
            "A workspace/filesystem error -- on-disk state may be "
            "inconsistent; restarting from an earlier checkpoint is safer "
            "than retrying in place."
        ),
    ),
    RecoveryReason.USER_CANCELLED: RecoveryRecommendation(
        mode=RecoveryMode.RESUME,
        confidence=0.9,
        explanation="Cancelled, not failed -- resuming continues exactly where it left off.",
    ),
    RecoveryReason.UNKNOWN: RecoveryRecommendation(
        mode=RecoveryMode.DUPLICATE_AND_RETRY,
        confidence=0.3,
        explanation="Cause not confidently classified -- a fresh duplicate avoids retrying into an unknown state.",
    ),
}


def recommend_action(
    reason: RecoveryReason,
    *,
    repeated_failure: bool = False,
    mode_success_rates: dict[str, float] | None = None,
) -> RecoveryRecommendation:

    base = _BASELINE.get(reason, _BASELINE[RecoveryReason.UNKNOWN])

    if repeated_failure and reason == RecoveryReason.PYTEST_FAILURE:
        return RecoveryRecommendation(
            mode=RecoveryMode.RESTART_WORKFLOW,
            confidence=0.35,
            explanation=(
                "This is the same failure as the previous attempt -- the "
                "last repair did not change the outcome. A full restart or "
                "a revised request is more likely to help than retrying again."
            ),
        )

    if mode_success_rates:
        observed = mode_success_rates.get(base.mode.value)

        if observed is not None:
            blended_confidence = round((base.confidence + observed) / 2, 2)

            return RecoveryRecommendation(
                mode=base.mode, confidence=blended_confidence, explanation=base.explanation
            )

    return base
