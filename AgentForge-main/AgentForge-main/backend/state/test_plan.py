from __future__ import annotations

from pydantic import BaseModel, Field


class TestStage(BaseModel):

    __test__ = False

    name: str = Field(..., description="e.g. 'compile_check', 'full_suite'.")
    command: list[str] = Field(..., description="Exact command tokens, never a shell string.")


class TestPlan(BaseModel):

    __test__ = False

    framework: str = Field(
        ...,
        description="'pytest', 'unittest', 'npm-script', 'jest', 'vitest', or 'none'.",
    )
    runtime: str = Field(..., description="'python' or 'node'.")
    working_directory: str = Field(
        ...,
        description="Relative path from project root this plan's commands must run from ('.' for root).",
    )
    stages: list[TestStage] = Field(
        default_factory=list,
        description="Ordered, progressive verification stages. Empty when no verification is possible.",
    )
    targeted_test_capability: bool = Field(
        default=False,
        description="Whether TestingService.build_targeted_command can safely narrow this plan's suite.",
    )
    test_files: list[str] = Field(
        default_factory=list,
        description="Relative paths of detected test files.",
    )
    configuration_files: list[str] = Field(
        default_factory=list,
        description="Relative paths of test/framework configuration files found (e.g. pytest.ini, jest.config.js).",
    )
    dependency_manifest: str | None = Field(
        default=None,
        description="Relative path to the dependency manifest for this sub-project, e.g. 'backend/requirements.txt'.",
    )
    package_manager: str | None = Field(
        default=None,
        description="'pip' or 'npm', when a dependency_manifest was found.",
    )
