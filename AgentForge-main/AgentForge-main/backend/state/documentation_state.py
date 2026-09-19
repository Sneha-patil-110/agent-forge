from pydantic import BaseModel, ConfigDict, Field


class DocumentationFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(
        ...,
        min_length=1,
        description="Title of the documentation file.",
    )

    path: str = Field(
        ...,
        min_length=1,
        description="Relative project path of the documentation file.",
    )

    content: str = Field(
        ...,
        min_length=1,
        description="Complete documentation file content.",
    )

    description: str | None = Field(
        default=None,
        description="Brief description of the documentation file.",
    )


class DocumentationState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_docs: list[DocumentationFile] = Field(
        default_factory=list,
        max_length=6,
        description="Generated documentation files.",
    )

    documentation_summary: str | None = Field(
        default=None,
        description="High level summary of the generated documentation.",
    )

    pending_documentation: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="Documentation that still needs to be generated.",
    )

    written_files: list[str] = Field(default_factory=list)

    file_write_errors: list[str] = Field(default_factory=list)