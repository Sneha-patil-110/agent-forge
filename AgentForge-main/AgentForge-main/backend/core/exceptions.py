from __future__ import annotations

from typing import Any


class AgentForgeException(Exception):
    def __init__(
        self,
        message: str = "An unexpected error occurred.",
        *,
        details: Any | None = None,
        error_code: str | None = None,
    ) -> None:
        self.message = message
        self.details = details
        self.error_code = error_code
        super().__init__(message)

    def __str__(self) -> str:
        return self.message



class ConfigurationError(AgentForgeException):
    pass


class AuthenticationError(AgentForgeException):
    pass


class AuthorizationError(AgentForgeException):
    pass



class LLMError(AgentForgeException):
    pass


class ProviderUnavailableError(LLMError):
    pass


class ModelNotFoundError(LLMError):
    pass


class RateLimitExceededError(LLMError):
    pass


class TokenLimitExceededError(LLMError):
    pass



class PromptNotFoundError(AgentForgeException):
    pass



class WorkflowError(AgentForgeException):
    pass


class InvalidWorkflowStateError(WorkflowError):
    pass


class WorkflowInterruptedError(WorkflowError):
    pass



class AgentExecutionError(AgentForgeException):
    pass


class AgentValidationError(AgentForgeException):
    pass


class AgentOutputEmptyError(AgentValidationError):
    def __init__(self, message: str = "Agent returned an empty response.", details: Any | None = None) -> None:
        super().__init__(message, details=details, error_code="AGENT_OUTPUT_EMPTY")


class AgentOutputTruncatedError(AgentValidationError):
    def __init__(self, message: str = "Agent response was truncated by provider token limit.", details: Any | None = None) -> None:
        super().__init__(message, details=details, error_code="AGENT_OUTPUT_TRUNCATED")


class AgentOutputInvalidJSONError(AgentValidationError):
    def __init__(self, message: str = "Agent returned syntactically invalid JSON.", details: Any | None = None) -> None:
        super().__init__(message, details=details, error_code="AGENT_OUTPUT_INVALID_JSON")


class AgentOutputSchemaError(AgentValidationError):
    def __init__(self, message: str = "Agent output failed schema validation.", details: Any | None = None) -> None:
        super().__init__(message, details=details, error_code="AGENT_OUTPUT_SCHEMA_ERROR")




class ToolError(AgentForgeException):
    pass


class ToolExecutionError(ToolError):
    pass


class UnsupportedToolOperationError(ToolError):
    pass


class FileSystemError(ToolError):
    pass


class TerminalExecutionError(ToolError):
    pass


class GitRepositoryError(ToolError):
    pass


class SearchError(ToolError):
    pass



class MCPError(AgentForgeException):
    pass


class MCPConfigurationError(MCPError):
    pass


class MCPConnectionError(MCPError):
    pass


class MCPServerNotFoundError(MCPError):
    pass


class MCPToolNotFoundError(MCPError):
    pass


class MCPDuplicateToolError(MCPError):
    pass


class MCPPermissionDeniedError(MCPError):
    pass


class MCPToolExecutionError(MCPError):
    pass


class MCPTimeoutError(MCPToolExecutionError):
    pass



class DatabaseError(AgentForgeException):
    pass



class ProjectNotFoundError(AgentForgeException):
    pass


class InvalidProjectIdError(AgentForgeException):
    pass


class ArtifactNotFoundError(AgentForgeException):
    pass



class ValidationError(AgentForgeException):
    pass



class RunError(AgentForgeException):
    pass


class InvalidRunIdError(RunError):
    pass


class RunNotFoundError(RunError):
    pass


class RunCorruptedError(RunError):
    pass


class RunAlreadyResumingError(RunError):
    pass



class KnowledgeError(AgentForgeException):
    pass


class KnowledgeEntryNotFoundError(KnowledgeError):
    pass



class RateLimitError(AgentForgeException):
    pass



class RepositoryError(AgentForgeException):
    pass


class RepositoryPathNotFoundError(RepositoryError):
    pass


class RepositoryPathAlreadyExistsError(RepositoryError):
    pass


class InvalidRepositoryPathError(RepositoryError):
    pass


class RepositoryConflictError(RepositoryError):
    pass


class RepositoryFileNotTextError(RepositoryError):
    pass



class PathValidationError(RepositoryError):
    pass


class WorkspaceContainmentError(RepositoryError):
    pass


class MaterializationError(RepositoryError):
    pass


class RepositoryIntegrityError(RepositoryError):
    pass


class StaticValidationError(ValidationError):
    pass

