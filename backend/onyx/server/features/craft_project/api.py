from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from onyx.auth.permissions import require_permission
from onyx.db.craft_project import (
    count_project_sessions,
    create_project,
    delete_project,
    delete_project_file,
    get_project_file,
    list_project_files,
    list_project_sessions,
    list_projects_for_user,
    replace_uploaded_project_file,
    require_project_for_user,
    require_project_write_for_user,
    store_uploaded_project_file,
    update_project,
)
from onyx.db.engine.sql_engine import get_session
from onyx.db.enums import Permission
from onyx.db.models import User
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.file_store.file_store import get_default_file_store
from onyx.server.features.build.api import require_onyx_craft_enabled
from onyx.server.features.build.db.sandbox import get_sandbox_by_user_id
from onyx.server.features.build.session.manager import SessionManager
from onyx.server.features.build.session.models import (
    DetailedSessionResponse,
    SessionResponse,
)
from onyx.server.features.craft_project.models import (
    CraftProjectCreateSessionRequest,
    CraftProjectFileResponse,
    CraftProjectListResponse,
    CraftProjectPatchRequest,
    CraftProjectResponse,
    CraftProjectUpsertRequest,
)
from onyx.server.query_and_chat.chat_utils import (
    is_spreadsheet_mime_type,
    parse_spreadsheet_for_preview,
)

router = APIRouter(
    prefix="/craft-projects",
    dependencies=[Depends(require_onyx_craft_enabled)],
)


def _summary(db_session: Session, project) -> CraftProjectResponse:
    files = list_project_files(db_session, project.id)
    return CraftProjectResponse.from_model(
        project,
        file_count=len(files),
        session_count=count_project_sessions(db_session, project.id),
    )


def _detail(db_session: Session, project) -> CraftProjectResponse:
    files = list_project_files(db_session, project.id)
    sessions = list_project_sessions(db_session, project.id)
    return CraftProjectResponse.from_model(
        project,
        file_count=len(files),
        session_count=len(sessions),
        files=files,
        sessions=sessions,
    )


@router.get("")
def list_craft_projects(
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> CraftProjectListResponse:
    rows = list_projects_for_user(db_session, user)
    return CraftProjectListResponse(
        projects=[_summary(db_session, row) for row in rows]
    )


@router.post("")
def create_craft_project(
    request: CraftProjectUpsertRequest,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> CraftProjectResponse:
    project = create_project(
        db_session,
        user=user,
        name=request.name,
        description=request.description,
        instructions=request.instructions,
        user_group_id=request.user_group_id,
    )
    return _detail(db_session, project)


@router.get("/{project_id}")
def get_craft_project(
    project_id: UUID,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> CraftProjectResponse:
    project = require_project_for_user(db_session, project_id, user)
    return _detail(db_session, project)


@router.patch("/{project_id}")
def patch_craft_project(
    project_id: UUID,
    request: CraftProjectPatchRequest,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> CraftProjectResponse:
    project = require_project_write_for_user(db_session, project_id, user)
    project = update_project(
        db_session,
        project,
        name=request.name,
        description=request.description,
        instructions=request.instructions,
        user_group_id=request.user_group_id,
        set_user_group="user_group_id" in request.model_fields_set,
        acting_user=user,
    )
    return _detail(db_session, project)


@router.delete("/{project_id}")
def delete_craft_project(
    project_id: UUID,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> Response:
    project = require_project_write_for_user(db_session, project_id, user)
    delete_project(db_session, project)
    return Response(status_code=204)


@router.get("/{project_id}/files")
def list_craft_project_files(
    project_id: UUID,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> list[CraftProjectFileResponse]:
    project = require_project_for_user(db_session, project_id, user)
    return [
        CraftProjectFileResponse.from_model(row)
        for row in list_project_files(db_session, project.id)
    ]


@router.post("/{project_id}/files")
def upload_craft_project_file(
    project_id: UUID,
    file: UploadFile = File(...),
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> CraftProjectFileResponse:
    project = require_project_write_for_user(db_session, project_id, user)
    content = file.file.read()
    row = store_uploaded_project_file(
        db_session,
        project=project,
        filename=file.filename or "upload.bin",
        content=content,
        content_type=file.content_type,
    )
    return CraftProjectFileResponse.from_model(row)


@router.get("/{project_id}/files/{file_id}")
def download_craft_project_file(
    project_id: UUID,
    file_id: UUID,
    parsed: bool = Query(False),
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> Response:
    project = require_project_for_user(db_session, project_id, user)
    row = get_project_file(db_session, project.id, file_id)
    filename = row.path.rsplit("/", 1)[-1]
    mime_type = row.mime_type or "application/octet-stream"
    is_xlsx = filename.lower().endswith((".xlsx", ".xlsm"))
    if parsed and (is_spreadsheet_mime_type(mime_type) or is_xlsx):
        with get_default_file_store().read_file(
            row.file_id, mode="b", use_tempfile=True
        ) as xlsx_io:
            preview = parse_spreadsheet_for_preview(xlsx_io, filename)
        return JSONResponse(content=preview.model_dump())
    content = get_default_file_store().read_file(row.file_id).read()
    return Response(
        content=content,
        media_type=mime_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.put("/{project_id}/files/{file_id}")
def replace_craft_project_file(
    project_id: UUID,
    file_id: UUID,
    file: UploadFile = File(...),
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> CraftProjectFileResponse:
    """Replace the bytes of an existing project file. Keep the same file id."""
    project = require_project_write_for_user(db_session, project_id, user)
    row = get_project_file(db_session, project.id, file_id)
    content = file.file.read()
    updated = replace_uploaded_project_file(
        db_session,
        project=project,
        row=row,
        content=content,
        content_type=file.content_type,
    )
    return CraftProjectFileResponse.from_model(updated)


@router.delete("/{project_id}/files/{file_id}")
def delete_craft_project_file_endpoint(
    project_id: UUID,
    file_id: UUID,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> Response:
    project = require_project_write_for_user(db_session, project_id, user)
    row = get_project_file(db_session, project.id, file_id)
    delete_project_file(db_session, row)
    return Response(status_code=204)


@router.post("/{project_id}/sessions")
def create_craft_project_session(
    project_id: UUID,
    request: CraftProjectCreateSessionRequest,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> DetailedSessionResponse:
    project = require_project_for_user(db_session, project_id, user)
    session_manager = SessionManager(db_session)
    build_session = session_manager.create_session(
        user.id,
        name=request.name or project.name,
        project_id=project.id,
        headless=request.headless,
    )
    sandbox = get_sandbox_by_user_id(db_session, user.id)
    if sandbox is None:
        raise OnyxError(OnyxErrorCode.SERVICE_UNAVAILABLE, "Sandbox is not ready")
    base = SessionResponse.from_model(build_session, sandbox)
    return DetailedSessionResponse.from_session_response(
        base, session_loaded_in_sandbox=True
    )
