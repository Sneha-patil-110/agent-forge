from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from backend.services.tracing_service import TracingService

_TOOL_CATEGORIES = {
    "filesystem": "filesystem",
    "terminal": "process",
    "git": "vcs",
    "search": "search",
}


class ToolResult(BaseModel):
    success: bool = Field(
        ...,
        description="Whether the tool executed successfully.",
    )

    output: Any | None = Field(
        default=None,
        description="Output produced by the tool.",
    )

    error: str | None = Field(
        default=None,
        description="Error message when execution fails.",
    )

    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional execution information.",
    )


class BaseTool(ABC):
    def __init__(
        self,
        *,
        tracing_service: TracingService | None = None,
    ) -> None:
        self.tracing_service = tracing_service or TracingService.disabled()

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        ...

    def validate_arguments(
        self,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return kwargs

    @abstractmethod
    def execute(
        self,
        **kwargs: Any,
    ) -> ToolResult:
        pass

    def run(
        self,
        **kwargs: Any,
    ) -> ToolResult:
        with self.tracing_service.trace(
            f"tool:{self.name}",
            run_type="tool",
            tags=[f"tool:{self.name}"],
            metadata={
                "tool_name": self.name,
                "tool_type": type(self).__name__,
                "tool_category": _TOOL_CATEGORIES.get(self.name, "tool"),
                "argument_count": len(kwargs),
            },
        ) as run:
            started_at = time.perf_counter()

            try:
                validated_arguments = self.validate_arguments(
                    **kwargs,
                )

                result = self.execute(
                    **validated_arguments,
                )

                if not isinstance(result, ToolResult):
                    result = ToolResult(
                        success=True,
                        output=result,
                    )

            except Exception as error:
                result = ToolResult(
                    success=False,
                    error=str(error),
                    metadata={
                        "tool": self.name,
                        "error_type": type(error).__name__,
                    },
                )

            self.tracing_service.set_outputs(
                run,
                {
                    "success": result.success,
                    "result_size": _result_size(result.output),
                    "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
                },
                error=None if result.success else result.error,
            )

            return result


def _result_size(output: Any) -> int:

    if output is None:
        return 0

    if isinstance(output, (str, bytes)):
        return len(output)

    if isinstance(output, (list, tuple, dict, set)):
        return len(output)

    return len(str(output))
