from __future__ import annotations

from pydantic import BaseModel, Field


class GeneratedCode(BaseModel):
    path: str = Field(
        ...,
        description="Relative project path of the generated file.",
    )

    content: str = Field(
        ...,
        description="Complete source file content.",
    )

    language: str = Field(
        ...,
        description="Programming or markup language of the file.",
    )

    description: str | None = Field(
        default=None,
        description="Brief description of the generated file.",
    )


class ImplementationState(BaseModel):

    generated_code: list[GeneratedCode] = Field(
        default_factory=list,
        description="List of generated code files.",
    )

    completed_tasks: list[str] = Field(
        default_factory=list,
        description="List of completed tasks in the implementation phase.",
    )

    failed_tasks: list[str] = Field(
        default_factory=list,
        description="List of failed tasks in the implementation phase.",
    )

    implementation_notes: str | None = Field(
        default=None,
        description="Notes and observations during the implementation phase.",
    )

    written_files: list[str] = Field(
        default_factory=list,
        description=(
            "Relative paths of generated files successfully written "
            "to disk by the materialization step. System controlled."
        ),
    )

    file_write_errors: list[str] = Field(
        default_factory=list,
        description=(
            "Errors encountered while materializing generated files "
            "to disk. System controlled."
        ),
    )
