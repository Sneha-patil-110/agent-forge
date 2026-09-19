
from __future__ import annotations

import hashlib
import re
from pathlib import PurePosixPath

from fastapi import APIRouter, Depends, Query, Response, status

from backend.api.dependencies import get_application, get_current_user, get_db_session, get_owned_run
from backend.api.schemas.repository import (
    CreateFileRequest,
    CreateFolderRequest,
    DiffResponse,
    DocumentationFileOut,
    DocumentationListResponse,
    DuplicateRequest,
    FileMetadataOut,
    FileReadResponse,
    FileVersionListResponse,
    FileVersionOut,
    FileWriteResponse,
    MoveRequest,
    PathResponse,
    RenameRequest,
    RepoFileNodeOut,
    RepoTreeResponse,
    SearchResponse,
    SearchResultOut,
    UpdateFileRequest,
)
from backend.core.app import Application
from backend.core.exceptions import InvalidRepositoryPathError, RepositoryPathNotFoundError
from backend.db.models.user import User
from backend.repositories.file_version_repository import FileVersionRepository
from backend.services.repository_service import RepoFileNode
from backend.state.run_metadata import RunMetadata

router = APIRouter(prefix="/api/v1/runs/{run_id}/repo", tags=["repository"])


def _to_node_out(node: RepoFileNode) -> RepoFileNodeOut:
    return RepoFileNodeOut(
        type=node.type,
        name=node.name,
        path=node.path,
        size_bytes=node.size_bytes,
        children=[_to_node_out(child) for child in node.children],
    )


def _output_directory(application: Application, run_id: str) -> str:
    state = application.run_service.load_state(run_id)

    if not state.project.output_directory:
        return ""

    output_directory = state.project.output_directory
    application.repository_service.ensure_materialized(
        run_id=run_id, state=state, output_directory=output_directory
    )

    return output_directory


def _version_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", name).strip("-")
    return cleaned or "project"


@router.get("/download")
def download_repository_archive(
    application: Application = Depends(get_application),
    metadata: RunMetadata = Depends(get_owned_run),
) -> Response:
    output_directory = _output_directory(application, metadata.run_id)

    if not output_directory:
        raise RepositoryPathNotFoundError("No generated files are available for this run yet.")

    state = application.run_service.load_state(metadata.run_id)
    archive_bytes = application.repository_service.build_zip_archive(output_directory)
    filename = f"{_safe_filename(state.project.project_name or metadata.run_id)}.zip"

    return Response(
        content=archive_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/tree", response_model=RepoTreeResponse)
def get_tree(
    application: Application = Depends(get_application),
    metadata: RunMetadata = Depends(get_owned_run),
) -> RepoTreeResponse:
    output_directory = _output_directory(application, metadata.run_id)
    tree = application.repository_service.get_tree(output_directory)

    return RepoTreeResponse(run_id=metadata.run_id, tree=[_to_node_out(node) for node in tree])


@router.post("/files", response_model=FileWriteResponse, status_code=status.HTTP_201_CREATED)
def create_file(
    payload: CreateFileRequest,
    application: Application = Depends(get_application),
    metadata: RunMetadata = Depends(get_owned_run),
    current_user: User = Depends(get_current_user),
) -> FileWriteResponse:
    output_directory = _output_directory(application, metadata.run_id)
    application.repository_service.create_file(
        run_id=metadata.run_id,
        output_directory=output_directory,
        path=payload.path,
        content=payload.content,
        actor=current_user.email,
    )

    return FileWriteResponse(path=payload.path, version=_version_hash(payload.content))


@router.put("/files/{path:path}", response_model=FileWriteResponse)
def update_file(
    path: str,
    payload: UpdateFileRequest,
    application: Application = Depends(get_application),
    metadata: RunMetadata = Depends(get_owned_run),
    current_user: User = Depends(get_current_user),
) -> FileWriteResponse:
    output_directory = _output_directory(application, metadata.run_id)
    application.repository_service.update_file(
        run_id=metadata.run_id,
        output_directory=output_directory,
        path=path,
        content=payload.content,
        actor=current_user.email,
        expected_version=payload.expected_version,
    )

    return FileWriteResponse(path=path, version=_version_hash(payload.content))


@router.delete("/files/{path:path}", status_code=status.HTTP_204_NO_CONTENT)
def delete_file(
    path: str,
    application: Application = Depends(get_application),
    metadata: RunMetadata = Depends(get_owned_run),
) -> None:
    output_directory = _output_directory(application, metadata.run_id)
    application.repository_service.delete_file(
        run_id=metadata.run_id, output_directory=output_directory, path=path
    )


@router.post("/files/{path:path}/rename", response_model=PathResponse)
def rename_file(
    path: str,
    payload: RenameRequest,
    application: Application = Depends(get_application),
    metadata: RunMetadata = Depends(get_owned_run),
) -> PathResponse:
    output_directory = _output_directory(application, metadata.run_id)
    new_path = application.repository_service.rename_file(
        run_id=metadata.run_id, output_directory=output_directory, path=path, new_name=payload.new_name
    )

    return PathResponse(path=new_path)


@router.post("/files/{path:path}/move", response_model=PathResponse)
def move_file(
    path: str,
    payload: MoveRequest,
    application: Application = Depends(get_application),
    metadata: RunMetadata = Depends(get_owned_run),
) -> PathResponse:
    output_directory = _output_directory(application, metadata.run_id)
    application.repository_service.move_file(
        run_id=metadata.run_id, output_directory=output_directory, path=path, destination=payload.destination
    )

    return PathResponse(path=payload.destination)


@router.post("/files/{path:path}/duplicate", response_model=PathResponse, status_code=status.HTTP_201_CREATED)
def duplicate_file(
    path: str,
    payload: DuplicateRequest,
    application: Application = Depends(get_application),
    metadata: RunMetadata = Depends(get_owned_run),
    current_user: User = Depends(get_current_user),
) -> PathResponse:
    output_directory = _output_directory(application, metadata.run_id)
    application.repository_service.duplicate_file(
        run_id=metadata.run_id,
        output_directory=output_directory,
        path=path,
        destination=payload.destination,
        actor=current_user.email,
    )

    return PathResponse(path=payload.destination)


@router.get("/files/{path:path}/metadata", response_model=FileMetadataOut)
def get_file_metadata(
    path: str,
    application: Application = Depends(get_application),
    metadata: RunMetadata = Depends(get_owned_run),
) -> FileMetadataOut:
    output_directory = _output_directory(application, metadata.run_id)
    state = application.run_service.load_state(metadata.run_id)
    file_metadata = application.repository_service.get_metadata(
        output_directory,
        path,
        run_id=metadata.run_id,
        documentation_paths=frozenset(f.path for f in state.documentation.generated_docs),
        developer_written_paths=frozenset(state.implementation.written_files),
    )

    return FileMetadataOut(
        path=file_metadata.path,
        size_bytes=file_metadata.size_bytes,
        language=file_metadata.language,
        last_modified=file_metadata.last_modified,
        generated_by_ai=file_metadata.generated_by_ai,
        last_edited_by=file_metadata.last_edited_by,
        agent=file_metadata.agent,
    )


@router.get("/files/{path:path}/versions", response_model=FileVersionListResponse)
def list_file_versions(
    path: str,
    metadata: RunMetadata = Depends(get_owned_run),
    session=Depends(get_db_session),
) -> FileVersionListResponse:
    records = FileVersionRepository(session).list_for_file(metadata.run_id, path)

    return FileVersionListResponse(
        path=path,
        versions=[
            FileVersionOut(id=r.id, source=r.source, edited_by=r.edited_by, created_at=r.created_at)
            for r in records
        ],
    )


@router.get("/files/{path:path}/diff", response_model=DiffResponse)
def diff_file(
    path: str,
    from_: str = Query(default="1", alias="from"),
    to: str = "current",
    application: Application = Depends(get_application),
    metadata: RunMetadata = Depends(get_owned_run),
    session=Depends(get_db_session),
) -> DiffResponse:
    output_directory = _output_directory(application, metadata.run_id)

    def _resolve(version_param: str) -> str:
        if version_param == "current":
            return application.repository_service.read_file(output_directory, path)

        try:
            version_id = int(version_param)
        except ValueError as error:
            raise InvalidRepositoryPathError(f"Invalid version identifier: {version_param!r}.") from error

        record = FileVersionRepository(session).get(version_id)

        if record is None or record.run_id != metadata.run_id or record.path != path:
            raise RepositoryPathNotFoundError(f"Version not found: {version_param}")

        return record.content

    return DiffResponse(
        path=path,
        from_version=from_,
        to_version=to,
        from_content=_resolve(from_),
        to_content=_resolve(to),
    )


@router.get("/files/{path:path}", response_model=FileReadResponse)
def read_file(
    path: str,
    application: Application = Depends(get_application),
    metadata: RunMetadata = Depends(get_owned_run),
) -> FileReadResponse:
    output_directory = _output_directory(application, metadata.run_id)
    content = application.repository_service.read_file(output_directory, path)

    return FileReadResponse(path=path, content=content, version=_version_hash(content))


@router.post("/folders", response_model=PathResponse, status_code=status.HTTP_201_CREATED)
def create_folder(
    payload: CreateFolderRequest,
    application: Application = Depends(get_application),
    metadata: RunMetadata = Depends(get_owned_run),
) -> PathResponse:
    output_directory = _output_directory(application, metadata.run_id)
    application.repository_service.create_folder(
        run_id=metadata.run_id, output_directory=output_directory, path=payload.path
    )

    return PathResponse(path=payload.path)


@router.delete("/folders/{path:path}", status_code=status.HTTP_204_NO_CONTENT)
def delete_folder(
    path: str,
    application: Application = Depends(get_application),
    metadata: RunMetadata = Depends(get_owned_run),
) -> None:
    output_directory = _output_directory(application, metadata.run_id)
    application.repository_service.delete_folder(
        run_id=metadata.run_id, output_directory=output_directory, path=path
    )


@router.post("/folders/{path:path}/rename", response_model=PathResponse)
def rename_folder(
    path: str,
    payload: RenameRequest,
    application: Application = Depends(get_application),
    metadata: RunMetadata = Depends(get_owned_run),
) -> PathResponse:
    output_directory = _output_directory(application, metadata.run_id)
    new_path = application.repository_service.rename_folder(
        run_id=metadata.run_id, output_directory=output_directory, path=path, new_name=payload.new_name
    )

    return PathResponse(path=new_path)


@router.post("/folders/{path:path}/move", response_model=PathResponse)
def move_folder(
    path: str,
    payload: MoveRequest,
    application: Application = Depends(get_application),
    metadata: RunMetadata = Depends(get_owned_run),
) -> PathResponse:
    output_directory = _output_directory(application, metadata.run_id)
    application.repository_service.move_folder(
        run_id=metadata.run_id, output_directory=output_directory, path=path, destination=payload.destination
    )

    return PathResponse(path=payload.destination)


@router.get("/search", response_model=SearchResponse)
def search_repository(
    q: str,
    mode: str = "filename",
    language: str | None = None,
    application: Application = Depends(get_application),
    metadata: RunMetadata = Depends(get_owned_run),
) -> SearchResponse:
    output_directory = _output_directory(application, metadata.run_id)
    matches = application.repository_service.search(output_directory, query=q, mode=mode, language=language)

    return SearchResponse(
        matches=[SearchResultOut(path=m.path, line=m.line, snippet=m.snippet) for m in matches]
    )


@router.get("/documentation", response_model=DocumentationListResponse)
def get_documentation(
    application: Application = Depends(get_application),
    metadata: RunMetadata = Depends(get_owned_run),
) -> DocumentationListResponse:
    state = application.run_service.load_state(metadata.run_id)
    db_metadata = application.repository_service.get_documentation_metadata(metadata.run_id)

    return DocumentationListResponse(
        documentation_summary=state.documentation.documentation_summary,
        files=[
            DocumentationFileOut(
                title=f.title,
                path=f.path,
                content=f.content,
                description=f.description,
                **db_metadata.get(f.path, {}),
            )
            for f in state.documentation.generated_docs
        ],
    )


@router.get("/documentation/{path:path}/download")
def download_documentation_file(
    path: str,
    application: Application = Depends(get_application),
    metadata: RunMetadata = Depends(get_owned_run),
) -> Response:
    state = application.run_service.load_state(metadata.run_id)
    doc = next((f for f in state.documentation.generated_docs if f.path == path), None)

    if doc is None:
        raise RepositoryPathNotFoundError(f"Documentation file not found: {path}")

    filename = PurePosixPath(path).name

    return Response(
        content=doc.content,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
