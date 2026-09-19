from __future__ import annotations

from pathlib import Path
import pytest

from backend.core.exceptions import (
    MaterializationError,
    PathValidationError,
    RepositoryIntegrityError,
    WorkspaceContainmentError,
)
from backend.core.workspace_containment import resolve_project_destination
from backend.services.artifact_validator import ArtifactValidator
from backend.services.failure_classifier import FailureClassifier, FailureCategory
from backend.services.materialization_service import MaterializationService
from backend.services.repository_integrity_validator import RepositoryIntegrityValidator
from backend.state.artifact_manifest import ArtifactFile, ArtifactManifest
from backend.state.workflow_state import WorkflowState
from backend.state.implementation_state import GeneratedCode, ImplementationState
from backend.state.project_state import ProjectState
from backend.tools.filesystem_tool import FilesystemTool
from backend.tools.tool_registry import ToolRegistry



def test_artifact_validator_strips_project_id_prefix_using_path_components() -> None:
    validator = ArtifactValidator()
    manifest = ArtifactManifest(
        files=[
            ArtifactFile(path="proj_20260726_999999/backend/main.py", content="content_a"),
            ArtifactFile(path="proj_20260726_999999/frontend/src/App.tsx", content="content_b"),
            ArtifactFile(path="backend/tests/test_api.py", content="content_c"),
        ]
    )

    result = validator.validate_and_normalize(manifest, project_id="proj_20260726_999999")
    assert result.is_valid
    paths = [f.path for f in result.manifest.files]
    assert paths == [
        "backend/main.py",
        "frontend/src/App.tsx",
        "backend/tests/test_api.py",
    ]


def test_artifact_validator_does_not_strip_non_matching_project_id_prefix() -> None:
    validator = ArtifactValidator()
    manifest = ArtifactManifest(
        files=[
            ArtifactFile(path="proj_OTHER/backend/main.py", content="x"),
        ]
    )

    result = validator.validate_and_normalize(manifest, project_id="proj_20260726_999999")
    assert result.is_valid
    assert result.manifest.files[0].path == "proj_OTHER/backend/main.py"


def test_artifact_validator_rejects_path_traversal() -> None:
    validator = ArtifactValidator()
    manifest = ArtifactManifest(
        files=[
            ArtifactFile(path="../outside.py", content="x"),
            ArtifactFile(path="proj_123/../../escape.py", content="x"),
        ]
    )

    result = validator.validate_and_normalize(manifest, project_id="proj_123")
    assert not result.is_valid
    assert len(result.issues) == 2


def test_artifact_validator_rejects_absolute_paths() -> None:
    validator = ArtifactValidator()
    manifest = ArtifactManifest(
        files=[
            ArtifactFile(path="/etc/passwd", content="x"),
            ArtifactFile(path="C:\\Windows\\System32\\cmd.exe", content="x"),
        ]
    )

    result = validator.validate_and_normalize(manifest, project_id="proj_123")
    assert not result.is_valid
    assert len(result.issues) == 2


def test_artifact_validator_rejects_duplicate_paths() -> None:
    validator = ArtifactValidator()
    manifest = ArtifactManifest(
        files=[
            ArtifactFile(path="backend/main.py", content="v1"),
            ArtifactFile(path="backend\\main.py", content="v2"),
        ]
    )

    result = validator.validate_and_normalize(manifest)
    assert not result.is_valid
    assert "Duplicate target path" in result.issues[0].message



def test_workspace_containment_resolves_valid_relative_path(tmp_path: Path) -> None:
    proj_root = tmp_path / "proj_123"
    proj_root.mkdir()

    dest = resolve_project_destination(proj_root, "backend/main.py")
    assert dest == (proj_root / "backend" / "main.py").resolve()


def test_workspace_containment_rejects_traversal_attempts(tmp_path: Path) -> None:
    proj_root = tmp_path / "proj_123"
    proj_root.mkdir()

    with pytest.raises(WorkspaceContainmentError):
        resolve_project_destination(proj_root, "../../escape.py")



def test_atomic_materialization_creates_arbitrary_nested_directories(tmp_path: Path) -> None:
    registry = ToolRegistry()
    registry.register(FilesystemTool(workspace=tmp_path))
    service = MaterializationService(registry)

    proj_dir = tmp_path / "proj_nest_test"
    proj_dir.mkdir()

    project = ProjectState(output_directory=str(proj_dir))
    impl = ImplementationState(
        generated_code=[
            GeneratedCode(
                path="frontend/src/components/auth/forms/login.tsx",
                content="// Login component\n",
                language="typescript",
            ),
            GeneratedCode(
                path="backend/api/v1/routes/users.py",
                content="# Users route\n",
                language="python",
            ),
        ]
    )

    result = service.materialize(project=project, implementation=impl)
    assert result.file_write_errors == []
    assert set(result.written_files) == {
        "frontend/src/components/auth/forms/login.tsx",
        "backend/api/v1/routes/users.py",
    }

    assert (proj_dir / "frontend/src/components/auth/forms/login.tsx").read_text() == "// Login component\n"
    assert (proj_dir / "backend/api/v1/routes/users.py").read_text() == "# Users route\n"


def test_materialization_prevents_duplicate_project_folder_nesting(tmp_path: Path) -> None:
    registry = ToolRegistry()
    registry.register(FilesystemTool(workspace=tmp_path))
    service = MaterializationService(registry)

    proj_dir = tmp_path / "proj_20260726_nesting"
    proj_dir.mkdir()

    project = ProjectState(output_directory=str(proj_dir))
    impl = ImplementationState(
        generated_code=[
            GeneratedCode(
                path="proj_20260726_nesting/backend/main.py",
                content="app = FastAPI()",
                language="python",
            )
        ]
    )

    result = service.materialize(project=project, implementation=impl)
    assert result.file_write_errors == []
    assert (proj_dir / "backend/main.py").exists()
    assert not (proj_dir / "proj_20260726_nesting").exists()



def test_repository_integrity_validator_detects_missing_root() -> None:
    validator = RepositoryIntegrityValidator()
    res = validator.validate_repository("/nonexistent/directory/path")
    assert not res.is_valid
    assert res.issues[0].code == "PROJECT_ROOT_MISSING"


def test_repository_integrity_validator_detects_nested_duplicate_directory(tmp_path: Path) -> None:
    validator = RepositoryIntegrityValidator()
    proj_dir = tmp_path / "proj_dup"
    proj_dir.mkdir()

    nested_dup = proj_dir / "proj_dup"
    nested_dup.mkdir()

    res = validator.validate_repository(str(proj_dir))
    assert not res.is_valid
    assert res.issues[0].code == "DUPLICATE_NESTED_PROJECT_DIRECTORY"


def test_repository_integrity_validator_validates_diverse_project_types(tmp_path: Path) -> None:
    validator = RepositoryIntegrityValidator()

    cli_dir = tmp_path / "cli_project"
    cli_dir.mkdir()
    (cli_dir / "src").mkdir()
    (cli_dir / "src/main.py").write_text("print('cli')")

    res_cli = validator.validate_repository(str(cli_dir), written_files=["src/main.py"])
    assert res_cli.is_valid

    fe_dir = tmp_path / "frontend_project"
    fe_dir.mkdir()
    (fe_dir / "package.json").write_text("{}")
    (fe_dir / "src").mkdir()
    (fe_dir / "src/App.tsx").write_text("export default () => <div/>;")

    res_fe = validator.validate_repository(str(fe_dir), written_files=["package.json", "src/App.tsx"])
    assert res_fe.is_valid



def test_failure_classifier_classifies_errors() -> None:
    classifier = FailureClassifier()

    path_err = PathValidationError("Invalid path")
    path_res = classifier.classify(path_err)
    assert path_res.category == FailureCategory.PATH_VALIDATION_ERROR
    assert not path_res.is_transient
    assert path_res.recommended_action == "repair_artifacts"

    rate_res = classifier.classify("429 Too Many Requests: Rate limit exceeded")
    assert rate_res.category == FailureCategory.PROVIDER_ERROR
    assert rate_res.is_transient
    assert rate_res.recommended_action == "retry_provider"

    mcp_res = classifier.classify("MCP protocol error connection refused")
    assert mcp_res.category == FailureCategory.MCP_ERROR
    assert mcp_res.is_transient

    test_res = classifier.classify("pytest failed with exit code 1", stage="testing")
    assert test_res.category == FailureCategory.TEST_FAILURE
    assert not test_res.is_transient
    assert test_res.recommended_action == "debug_code"
