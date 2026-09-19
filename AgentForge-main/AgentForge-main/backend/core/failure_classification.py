from __future__ import annotations

import json
from enum import Enum

from pydantic import ValidationError as PydanticValidationError

from backend.core.exceptions import (
    AgentForgeException,
    AgentValidationError,
    ConfigurationError,
    AuthenticationError as AgentForgeAuthenticationError,
    DatabaseError,
    FileSystemError,
    InvalidWorkflowStateError,
    LLMError,
    MCPError,
    RepositoryError,
    RunCorruptedError,
    ToolError,
    WorkflowInterruptedError,
)


class FailureCategory(str, Enum):

    PROVIDER = "provider"
    VALIDATION = "validation"
    PARSING = "parsing"
    TOOL = "tool"
    CONTEXT_OVERFLOW = "context_overflow"
    TIMEOUT = "timeout"
    NETWORK = "network"
    AUTHENTICATION = "authentication"
    DATABASE = "database"
    WORKSPACE = "workspace"
    MCP = "mcp"
    FILESYSTEM = "filesystem"
    SERIALIZATION = "serialization"
    STATE_CORRUPTION = "state_corruption"
    PROMPT_CONSTRUCTION = "prompt_construction"
    UNKNOWN = "unknown"


_RETRYABLE_CATEGORIES = frozenset(
    {
        FailureCategory.PROVIDER,
        FailureCategory.TIMEOUT,
        FailureCategory.NETWORK,
        FailureCategory.DATABASE,
    }
)

_CONTEXT_OVERFLOW_MARKERS = (
    "context length",
    "context_length",
    "maximum context",
    "too many tokens",
    "context window",
)

_RATE_LIMIT_MARKERS = ("rate limit", "rate_limit", "quota")


def is_likely_retryable(category: FailureCategory) -> bool:
    return category in _RETRYABLE_CATEGORIES


def classify_exception(error: BaseException) -> FailureCategory:

    if isinstance(error, AgentForgeException) and error.__cause__ is not None:
        cause_category = classify_exception(error.__cause__)

        if cause_category is not FailureCategory.UNKNOWN:
            return cause_category

    status_code = getattr(error, "status_code", None) or getattr(error, "code", None)
    type_name = type(error).__name__
    module_name = type(error).__module__
    message = str(error).lower()

    if isinstance(status_code, int):
        if status_code == 429:
            return FailureCategory.PROVIDER
        if status_code in (401, 403):
            return FailureCategory.AUTHENTICATION
        if status_code in (408, 504):
            return FailureCategory.TIMEOUT
        if status_code == 400:
            if any(marker in message for marker in _CONTEXT_OVERFLOW_MARKERS):
                return FailureCategory.CONTEXT_OVERFLOW
            return FailureCategory.VALIDATION
        if status_code >= 500:
            return FailureCategory.PROVIDER

    if "ratelimit" in type_name.lower() or any(marker in message for marker in _RATE_LIMIT_MARKERS):
        return FailureCategory.PROVIDER
    if "timeout" in type_name.lower():
        return FailureCategory.TIMEOUT
    if "connection" in type_name.lower():
        return FailureCategory.NETWORK
    if "authentication" in type_name.lower() or "permissiondenied" in type_name.lower():
        return FailureCategory.AUTHENTICATION
    if any(marker in message for marker in _CONTEXT_OVERFLOW_MARKERS):
        return FailureCategory.CONTEXT_OVERFLOW
    if module_name.split(".")[0] in {"openai", "groq", "google", "anthropic", "cerebras_cloud_sdk"}:
        return FailureCategory.PROVIDER

    if isinstance(error, (PydanticValidationError, AgentValidationError)):
        return FailureCategory.VALIDATION
    if isinstance(error, json.JSONDecodeError):
        return FailureCategory.PARSING
    if isinstance(error, MCPError):
        return FailureCategory.MCP
    if isinstance(error, ToolError):
        return FailureCategory.TOOL
    if isinstance(error, DatabaseError):
        return FailureCategory.DATABASE
    if isinstance(error, FileSystemError):
        return FailureCategory.WORKSPACE
    if isinstance(error, RepositoryError):
        return FailureCategory.FILESYSTEM
    if isinstance(error, (InvalidWorkflowStateError, RunCorruptedError)):
        return FailureCategory.STATE_CORRUPTION
    if isinstance(error, WorkflowInterruptedError):
        return FailureCategory.UNKNOWN
    if isinstance(error, (AgentForgeAuthenticationError, ConfigurationError)):
        return FailureCategory.AUTHENTICATION
    if isinstance(error, LLMError):
        return FailureCategory.PROVIDER
    if isinstance(error, (OSError, FileNotFoundError, PermissionError)):
        return FailureCategory.FILESYSTEM
    if isinstance(error, (ConnectionError,)):
        return FailureCategory.NETWORK
    if isinstance(error, TimeoutError):
        return FailureCategory.TIMEOUT
    if isinstance(error, (ValueError, TypeError)) and "json" in message:
        return FailureCategory.PARSING

    return FailureCategory.UNKNOWN


class RecoveryReason(str, Enum):

    RATE_LIMIT = "rate_limit"
    NETWORK_TIMEOUT = "network_timeout"
    LLM_PARSE_ERROR = "llm_parse_error"
    INVALID_JSON = "invalid_json"
    DATABASE_ERROR = "database_error"
    PYTEST_FAILURE = "pytest_failure"
    REVIEW_FAILURE = "review_failure"
    USER_CANCELLED = "user_cancelled"
    WORKSPACE_ERROR = "workspace_error"
    UNKNOWN = "unknown"


def to_recovery_reason(
    *,
    category: FailureCategory | None,
    testing_failed: bool = False,
    review_failed: bool = False,
    user_cancelled: bool = False,
) -> RecoveryReason:
    if user_cancelled:
        return RecoveryReason.USER_CANCELLED
    if testing_failed:
        return RecoveryReason.PYTEST_FAILURE
    if review_failed:
        return RecoveryReason.REVIEW_FAILURE

    if category is None:
        return RecoveryReason.UNKNOWN

    return {
        FailureCategory.PROVIDER: RecoveryReason.RATE_LIMIT,
        FailureCategory.TIMEOUT: RecoveryReason.NETWORK_TIMEOUT,
        FailureCategory.NETWORK: RecoveryReason.NETWORK_TIMEOUT,
        FailureCategory.PARSING: RecoveryReason.LLM_PARSE_ERROR,
        FailureCategory.VALIDATION: RecoveryReason.INVALID_JSON,
        FailureCategory.SERIALIZATION: RecoveryReason.INVALID_JSON,
        FailureCategory.DATABASE: RecoveryReason.DATABASE_ERROR,
        FailureCategory.WORKSPACE: RecoveryReason.WORKSPACE_ERROR,
        FailureCategory.FILESYSTEM: RecoveryReason.WORKSPACE_ERROR,
    }.get(category, RecoveryReason.UNKNOWN)


def failure_signature(agent: str, reason: RecoveryReason, error_message: str | None) -> str:

    import hashlib

    normalized = (error_message or "").strip().lower()[:500]
    digest = hashlib.sha256(f"{agent}:{reason.value}:{normalized}".encode("utf-8")).hexdigest()

    return digest[:16]
