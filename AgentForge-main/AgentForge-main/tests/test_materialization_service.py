from __future__ import annotations

from pathlib import Path

import pytest

from backend.services.materialization_service import MaterializationService
from backend.state.documentation_state import DocumentationFile, DocumentationState
from backend.state.implementation_state import GeneratedCode, ImplementationState
from backend.state.project_state import ProjectState
from backend.tools.filesystem_tool import FilesystemTool
from backend.tools.tool_registry import ToolRegistry


@pytest.fixture
def service(tmp_path: Path) -> tuple[MaterializationService, Path]:
    registry = ToolRegistry()
    registry.register(FilesystemTool(workspace=tmp_path))

    return MaterializationService(registry), tmp_path


def test_does_not_write_when_output_directory_is_none(
    service: tuple[MaterializationService, Path],
) -> None:
    materialization_service, _ = service

    project = ProjectState(output_directory=None)
    implementation = ImplementationState(
        generated_code=[
            GeneratedCode(
                path="app.py", content="print(1)", language="python"
            )
        ]
    )

    result = materialization_service.materialize(
        project=project, implementation=implementation
    )

    assert result.written_files == []
    assert result.generated_code[0].content == "print(1)"


def test_writes_valid_generated_files(
    service: tuple[MaterializationService, Path],
) -> None:
    materialization_service, workspace = service

    output_dir = workspace / "my-project"
    output_dir.mkdir()

    project = ProjectState(output_directory=str(output_dir))
    implementation = ImplementationState(
        generated_code=[
            GeneratedCode(
                path="app.py", content="print(1)", language="python"
            )
        ]
    )

    result = materialization_service.materialize(
        project=project, implementation=implementation
    )

    assert result.written_files == ["app.py"]
    assert result.file_write_errors == []
    assert (output_dir / "app.py").read_text(encoding="utf-8") == "print(1)"


def test_rejects_absolute_path(
    service: tuple[MaterializationService, Path],
) -> None:
    materialization_service, workspace = service

    output_dir = workspace / "my-project"
    output_dir.mkdir()

    project = ProjectState(output_directory=str(output_dir))
    implementation = ImplementationState(
        generated_code=[
            GeneratedCode(
                path="/etc/passwd", content="x", language="text"
            )
        ]
    )

    result = materialization_service.materialize(
        project=project, implementation=implementation
    )

    assert result.written_files == []
    assert len(result.file_write_errors) == 1


def test_rejects_path_traversal(
    service: tuple[MaterializationService, Path],
) -> None:
    materialization_service, workspace = service

    output_dir = workspace / "my-project"
    output_dir.mkdir()

    project = ProjectState(output_directory=str(output_dir))
    implementation = ImplementationState(
        generated_code=[
            GeneratedCode(
                path="../../escape.py", content="x", language="python"
            )
        ]
    )

    result = materialization_service.materialize(
        project=project, implementation=implementation
    )

    assert result.written_files == []
    assert len(result.file_write_errors) == 1


def test_rejects_empty_path(
    service: tuple[MaterializationService, Path],
) -> None:
    materialization_service, workspace = service

    output_dir = workspace / "my-project"
    output_dir.mkdir()

    project = ProjectState(output_directory=str(output_dir))
    implementation = ImplementationState(
        generated_code=[
            GeneratedCode(path="", content="x", language="text")
        ]
    )

    result = materialization_service.materialize(
        project=project, implementation=implementation
    )

    assert result.written_files == []
    assert len(result.file_write_errors) == 1


def test_creates_nested_directories(
    service: tuple[MaterializationService, Path],
) -> None:
    materialization_service, workspace = service

    output_dir = workspace / "my-project"
    output_dir.mkdir()

    project = ProjectState(output_directory=str(output_dir))
    implementation = ImplementationState(
        generated_code=[
            GeneratedCode(
                path="backend/app/services/task_service.py",
                content="class TaskService:\n    pass\n",
                language="python",
            )
        ]
    )

    result = materialization_service.materialize(
        project=project, implementation=implementation
    )

    written_path = output_dir / "backend/app/services/task_service.py"

    assert result.written_files == ["backend/app/services/task_service.py"]
    assert written_path.exists()
    assert written_path.read_text(encoding="utf-8") == (
        "class TaskService:\n    pass\n"
    )


def test_preserves_complete_multiline_content(
    service: tuple[MaterializationService, Path],
) -> None:
    materialization_service, workspace = service

    output_dir = workspace / "my-project"
    output_dir.mkdir()

    content = (
        "def divide(a, b):\n"
        "    if b == 0:\n"
        "        raise ValueError('Cannot divide by zero')\n"
        "    return a / b\n"
    )

    project = ProjectState(output_directory=str(output_dir))
    implementation = ImplementationState(
        generated_code=[
            GeneratedCode(path="calc.py", content=content, language="python")
        ]
    )

    result = materialization_service.materialize(
        project=project, implementation=implementation
    )

    assert result.file_write_errors == []
    assert (output_dir / "calc.py").read_text(encoding="utf-8") == content


def test_partial_failure_is_recorded_alongside_successful_writes(
    service: tuple[MaterializationService, Path],
) -> None:
    materialization_service, workspace = service

    output_dir = workspace / "my-project"
    output_dir.mkdir()

    project = ProjectState(output_directory=str(output_dir))
    implementation = ImplementationState(
        generated_code=[
            GeneratedCode(path="good.py", content="ok", language="python"),
            GeneratedCode(path="/etc/bad.py", content="x", language="python"),
        ]
    )

    result = materialization_service.materialize(
        project=project, implementation=implementation
    )

    assert result.written_files == ["good.py"]
    assert len(result.file_write_errors) == 1
    assert "bad.py" in result.file_write_errors[0]


def test_output_directory_cannot_escape_into_agentforge_source(
    service: tuple[MaterializationService, Path],
) -> None:

    from backend.core.workspace import SOURCE_ROOT

    materialization_service, _ = service

    project = ProjectState(output_directory=str(SOURCE_ROOT))
    implementation = ImplementationState(
        generated_code=[
            GeneratedCode(
                path="malicious.py", content="x", language="python"
            )
        ]
    )

    result = materialization_service.materialize(
        project=project, implementation=implementation
    )

    assert result.written_files == []
    assert len(result.file_write_errors) == 1
    assert not (SOURCE_ROOT / "malicious.py").exists()


def test_preserves_previously_written_files_across_retries(
    service: tuple[MaterializationService, Path],
) -> None:
    materialization_service, workspace = service

    output_dir = workspace / "my-project"
    output_dir.mkdir()

    project = ProjectState(output_directory=str(output_dir))

    implementation = ImplementationState(
        generated_code=[
            GeneratedCode(path="fixed.py", content="x", language="python")
        ]
    )

    result = materialization_service.materialize(
        project=project,
        implementation=implementation,
        previous_written_files=["app.py"],
    )

    assert set(result.written_files) == {"app.py", "fixed.py"}


def test_repair_cycle_leaves_unrelated_file_content_byte_for_byte_unchanged(
    service: tuple[MaterializationService, Path],
) -> None:

    materialization_service, workspace = service

    output_dir = workspace / "my-project"
    output_dir.mkdir()

    project = ProjectState(output_directory=str(output_dir))

    initial = ImplementationState(
        generated_code=[
            GeneratedCode(path="file_a.py", content="a = 1\n", language="python"),
            GeneratedCode(path="file_b.py", content="b = 1\n", language="python"),
            GeneratedCode(path="file_c.py", content="c = 1\n", language="python"),
        ]
    )

    materialization_service.materialize(project=project, implementation=initial)

    file_a_path = output_dir / "file_a.py"
    file_c_path = output_dir / "file_c.py"

    assert file_a_path.read_text(encoding="utf-8") == "a = 1\n"
    assert file_c_path.read_text(encoding="utf-8") == "c = 1\n"

    repair = ImplementationState(
        generated_code=[
            GeneratedCode(path="file_b.py", content="b = 2  # fixed\n", language="python"),
        ]
    )

    result = materialization_service.materialize(
        project=project,
        implementation=repair,
        previous_written_files=initial.written_files,
    )

    assert (output_dir / "file_b.py").read_text(encoding="utf-8") == "b = 2  # fixed\n"

    assert file_a_path.read_text(encoding="utf-8") == "a = 1\n"
    assert file_c_path.read_text(encoding="utf-8") == "c = 1\n"

    assert set(result.written_files) == {"file_a.py", "file_b.py", "file_c.py"}
    assert result.file_write_errors == []


def test_materialize_documentation_writes_generated_docs(
    service: tuple[MaterializationService, Path],
) -> None:
    materialization_service, workspace = service

    output_dir = workspace / "my-project"
    output_dir.mkdir()

    project = ProjectState(output_directory=str(output_dir))
    documentation = DocumentationState(
        generated_docs=[
            DocumentationFile(title="Overview", path="README.md", content="# Overview\n"),
            DocumentationFile(title="API", path="docs/api.md", content="# API\n"),
        ]
    )

    result = materialization_service.materialize_documentation(
        project=project, documentation=documentation
    )

    assert set(result.written_files) == {"README.md", "docs/api.md"}
    assert result.file_write_errors == []
    assert (output_dir / "README.md").read_text(encoding="utf-8") == "# Overview\n"
    assert (output_dir / "docs" / "api.md").read_text(encoding="utf-8") == "# API\n"


def test_materialize_documentation_does_not_write_when_output_directory_is_none(
    service: tuple[MaterializationService, Path],
) -> None:
    materialization_service, _ = service

    project = ProjectState(output_directory=None)
    documentation = DocumentationState(
        generated_docs=[DocumentationFile(title="Overview", path="README.md", content="# Overview\n")]
    )

    result = materialization_service.materialize_documentation(project=project, documentation=documentation)

    assert result.written_files == []


def test_materialize_documentation_carries_forward_written_files_on_regeneration(
    service: tuple[MaterializationService, Path],
) -> None:

    materialization_service, workspace = service

    output_dir = workspace / "my-project"
    output_dir.mkdir()

    project = ProjectState(output_directory=str(output_dir))

    first_pass = DocumentationState(
        generated_docs=[
            DocumentationFile(title="Overview", path="README.md", content="# Overview\n"),
            DocumentationFile(title="Deploy", path="docs/deployment.md", content="# Deploy\n"),
        ]
    )
    first_result = materialization_service.materialize_documentation(
        project=project, documentation=first_pass
    )
    assert set(first_result.written_files) == {"README.md", "docs/deployment.md"}

    second_pass = DocumentationState(
        generated_docs=[
            DocumentationFile(title="Overview", path="README.md", content="# Overview v2\n"),
        ]
    )
    second_result = materialization_service.materialize_documentation(
        project=project,
        documentation=second_pass,
        previous_written_files=first_result.written_files,
    )

    assert set(second_result.written_files) == {"README.md", "docs/deployment.md"}
    assert (output_dir / "README.md").read_text(encoding="utf-8") == "# Overview v2\n"
    assert (output_dir / "docs" / "deployment.md").read_text(encoding="utf-8") == "# Deploy\n"


def test_strips_leading_project_directory_name_from_relative_path(
    service: tuple[MaterializationService, Path],
) -> None:
    materialization_service, workspace = service

    output_dir = workspace / "proj_20260726_5772afd8"
    output_dir.mkdir()

    project = ProjectState(output_directory=str(output_dir))
    implementation = ImplementationState(
        generated_code=[
            GeneratedCode(
                path="proj_20260726_5772afd8/backend/main.py",
                content="print('hello')",
                language="python",
            )
        ]
    )

    result = materialization_service.materialize(
        project=project, implementation=implementation
    )

    assert result.written_files == ["backend/main.py"]
    assert result.file_write_errors == []
    assert (output_dir / "backend" / "main.py").exists()
    assert (output_dir / "backend" / "main.py").read_text(encoding="utf-8") == "print('hello')"

