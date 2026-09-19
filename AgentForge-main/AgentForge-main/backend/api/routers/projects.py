from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status

from backend.api.dependencies import get_application, get_owned_run
from backend.api.schemas.projects import (
    ProjectFileContent,
    ProjectFileList,
    ProjectFileOut,
    RunProjectOut,
)
from backend.core.app import Application
from backend.state.run_metadata import RunMetadata

router = APIRouter(prefix="/api/v1/runs", tags=["projects"])


@router.get("/{run_id}/project", response_model=RunProjectOut)
def get_project(
    application: Application = Depends(get_application),
    metadata: RunMetadata = Depends(get_owned_run),
) -> RunProjectOut:
    state = application.run_service.load_state(metadata.run_id)
    project = state.project

    return RunProjectOut(
        run_id=metadata.run_id,
        project_name=project.project_name,
        project_description=project.project_description,
        objective=project.objective,
        status=project.status.value,
        backend=project.backend,
        frontend=project.frontend,
        database=project.database,
        deployment=project.deployment,
        requirements=project.requirements,
        tech_stack=project.tech_stack,
        output_directory=project.output_directory,
    )


@router.get("/{run_id}/files", response_model=ProjectFileList)
def list_project_files(
    application: Application = Depends(get_application),
    metadata: RunMetadata = Depends(get_owned_run),
) -> ProjectFileList:
    state = application.run_service.load_state(metadata.run_id)
    output_directory = state.project.output_directory

    files: list[ProjectFileOut] = []

    if output_directory:
        root = Path(output_directory)

        for relative_path in state.implementation.written_files:
            full_path = root / relative_path

            if full_path.is_file():
                files.append(ProjectFileOut(path=relative_path, size_bytes=full_path.stat().st_size))

    return ProjectFileList(run_id=metadata.run_id, files=files)


@router.get("/{run_id}/files/{file_path:path}", response_model=ProjectFileContent)
def get_project_file(
    file_path: str,
    application: Application = Depends(get_application),
    metadata: RunMetadata = Depends(get_owned_run),
) -> ProjectFileContent:
    state = application.run_service.load_state(metadata.run_id)
    output_directory = state.project.output_directory

    if not output_directory or file_path not in state.implementation.written_files:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"File not found: {file_path}")

    root = Path(output_directory).resolve()
    resolved = (root / file_path).resolve()

    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file path.") from error

    try:
        content = resolved.read_text(encoding="utf-8")
    except OSError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"File not found: {file_path}") from error

    return ProjectFileContent(path=file_path, content=content)
