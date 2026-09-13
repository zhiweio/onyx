"""Database operations for Craft Projects."""

from __future__ import annotations

import hashlib
import mimetypes
import re
from io import BytesIO
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from onyx.configs.constants import FileOrigin
from onyx.db.enums import CraftProjectFileSource
from onyx.db.models import (
    BuildSession,
    CraftProject,
    CraftProjectFile,
    User,
    User__UserGroup,
)
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.file_store.file_store import get_default_file_store
from onyx.server.features.build.configs import (
    CRAFT_DEEP_JOB_PROJECT_MAX_FILES,
    CRAFT_DEEP_JOB_RESOURCES,
    CRAFT_PROJECT_MAX_FILE_SIZE_BYTES,
    CRAFT_PROJECT_MAX_FILES,
    CRAFT_PROJECT_MAX_TOTAL_SIZE_BYTES,
)

# Drop control characters and characters that break paths. Keep letters
# from any script so a Chinese report name stays intact.
_UNSAFE_IN_SEGMENT = re.compile(r'[\x00-\x1f\x7f\\/:*?"<>|]+')
CRAFT_PROJECT_STORE_PREFIX = "craft/projects"
IMPLICIT_UNTITLED_PROJECT_NAME = "Untitled project"
_SESSION_WORKING_FILE_NAMES = frozenset(
    {
        "PLAN.md",
        "TODO.md",
        "MEMORY.md",
        "DONE.json",
        "PLAN.json",
    }
)


def project_file_limit(db_session: Session, project_id: UUID) -> int:
    if CRAFT_DEEP_JOB_RESOURCES:
        return CRAFT_DEEP_JOB_PROJECT_MAX_FILES
    from onyx.db.craft_job import project_has_craft_job

    if project_has_craft_job(db_session, project_id):
        return CRAFT_DEEP_JOB_PROJECT_MAX_FILES
    return CRAFT_PROJECT_MAX_FILES


def sanitize_project_path(path: str) -> str:
    """Return a /-prefixed path with traversal segments removed."""
    parts: list[str] = []
    for part in path.replace("\\", "/").split("/"):
        cleaned = _UNSAFE_IN_SEGMENT.sub("", part).strip()
        if not cleaned or cleaned in {".", ".."}:
            continue
        parts.append(cleaned)
    if not parts:
        raise OnyxError(OnyxErrorCode.INVALID_INPUT, "Path is empty")
    return "/" + "/".join(parts)


def _membership(
    db_session: Session, user_id: UUID, group_id: int
) -> User__UserGroup | None:
    return db_session.scalar(
        select(User__UserGroup).where(
            User__UserGroup.user_id == user_id,
            User__UserGroup.user_group_id == group_id,
        )
    )


def user_can_read_project(
    db_session: Session, project: CraftProject, user: User
) -> bool:
    if project.user_id == user.id:
        return True
    if project.user_group_id is None:
        return False
    return _membership(db_session, user.id, project.user_group_id) is not None


def user_can_write_project(
    db_session: Session, project: CraftProject, user: User
) -> bool:
    if project.user_id == user.id:
        return True
    if project.user_group_id is None:
        return False
    membership = _membership(db_session, user.id, project.user_group_id)
    if membership is None:
        return False
    return membership.is_curator or membership.is_manager


def require_project_for_user(
    db_session: Session, project_id: UUID, user: User
) -> CraftProject:
    project = db_session.get(CraftProject, project_id)
    if project is None or not user_can_read_project(db_session, project, user):
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Project not found")
    return project


def require_project_write_for_user(
    db_session: Session, project_id: UUID, user: User
) -> CraftProject:
    project = require_project_for_user(db_session, project_id, user)
    if not user_can_write_project(db_session, project, user):
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Project not found")
    return project


def implicit_untitled_project_clause() -> ColumnElement[bool]:
    """Auto-created home drafts used this exact empty Untitled project."""
    empty_instructions = or_(
        CraftProject.instructions.is_(None),
        CraftProject.instructions == "",
    )
    return and_(
        CraftProject.name == IMPLICIT_UNTITLED_PROJECT_NAME,
        empty_instructions,
        CraftProject.description == "",
    )


def is_implicit_untitled_project(project: CraftProject) -> bool:
    return (
        project.name == IMPLICIT_UNTITLED_PROJECT_NAME
        and not (project.instructions or "").strip()
        and not (project.description or "").strip()
    )


def list_projects_for_user(db_session: Session, user: User) -> list[CraftProject]:
    group_ids = select(User__UserGroup.user_group_id).where(
        User__UserGroup.user_id == user.id
    )
    return list(
        db_session.scalars(
            select(CraftProject)
            .where(
                or_(
                    CraftProject.user_id == user.id,
                    CraftProject.user_group_id.in_(group_ids),
                ),
                ~implicit_untitled_project_clause(),
            )
            .order_by(CraftProject.updated_at.desc())
        )
    )


def create_project__no_commit(
    db_session: Session,
    *,
    user: User,
    name: str,
    description: str = "",
    instructions: str | None = None,
    user_group_id: int | None = None,
) -> CraftProject:
    trimmed = name.strip()
    if not trimmed:
        raise OnyxError(OnyxErrorCode.INVALID_INPUT, "Name is required")
    if (
        user_group_id is not None
        and _membership(db_session, user.id, user_group_id) is None
    ):
        raise OnyxError(OnyxErrorCode.INVALID_INPUT, "Not a member of that group")
    project = CraftProject(
        user_id=user.id,
        name=trimmed[:128],
        description=description.strip(),
        instructions=instructions.strip() if instructions else None,
        user_group_id=user_group_id,
    )
    db_session.add(project)
    db_session.flush()
    return project


def create_project(
    db_session: Session,
    *,
    user: User,
    name: str,
    description: str = "",
    instructions: str | None = None,
    user_group_id: int | None = None,
) -> CraftProject:
    project = create_project__no_commit(
        db_session,
        user=user,
        name=name,
        description=description,
        instructions=instructions,
        user_group_id=user_group_id,
    )
    db_session.commit()
    db_session.refresh(project)
    return project


def update_project(
    db_session: Session,
    project: CraftProject,
    *,
    name: str | None = None,
    description: str | None = None,
    instructions: str | None = None,
    user_group_id: int | None = None,
    set_user_group: bool = False,
    acting_user: User | None = None,
) -> CraftProject:
    if name is not None:
        trimmed = name.strip()
        if not trimmed:
            raise OnyxError(OnyxErrorCode.INVALID_INPUT, "Name is required")
        project.name = trimmed[:128]
    if description is not None:
        project.description = description.strip()
    if instructions is not None:
        project.instructions = instructions.strip() or None
    if set_user_group:
        if acting_user is None or acting_user.id != project.user_id:
            raise OnyxError(OnyxErrorCode.NOT_FOUND, "Project not found")
        if (
            user_group_id is not None
            and _membership(db_session, acting_user.id, user_group_id) is None
        ):
            raise OnyxError(OnyxErrorCode.INVALID_INPUT, "Not a member of that group")
        project.user_group_id = user_group_id
    db_session.commit()
    db_session.refresh(project)
    return project


def delete_project(db_session: Session, project: CraftProject) -> None:
    file_store = get_default_file_store()
    for row in list_project_files(db_session, project.id, include_deleted=True):
        try:
            file_store.delete_file(row.file_id)
        except Exception:
            pass
    db_session.delete(project)
    db_session.commit()


def _is_auto_promoted_working_file(row: CraftProjectFile) -> bool:
    if row.source != CraftProjectFileSource.SESSION_OUTPUT:
        return False
    return row.path.rsplit("/", 1)[-1] in _SESSION_WORKING_FILE_NAMES


def retract_session_working_files(db_session: Session, project_id: UUID) -> None:
    """Soft-delete host working files that a session auto-promoted."""
    rows = db_session.scalars(
        select(CraftProjectFile).where(
            CraftProjectFile.project_id == project_id,
            CraftProjectFile.deleted.is_(False),
            CraftProjectFile.source == CraftProjectFileSource.SESSION_OUTPUT,
        )
    )
    changed = False
    for row in rows:
        if row.path.rsplit("/", 1)[-1] in _SESSION_WORKING_FILE_NAMES:
            row.deleted = True
            changed = True
    if changed:
        db_session.flush()


def list_project_files(
    db_session: Session,
    project_id: UUID,
    *,
    include_deleted: bool = False,
) -> list[CraftProjectFile]:
    query = select(CraftProjectFile).where(CraftProjectFile.project_id == project_id)
    if not include_deleted:
        query = query.where(CraftProjectFile.deleted.is_(False))
    rows = list(db_session.scalars(query.order_by(CraftProjectFile.path)))
    if include_deleted:
        return rows
    return [row for row in rows if not _is_auto_promoted_working_file(row)]


def get_project_file(
    db_session: Session, project_id: UUID, file_id: UUID
) -> CraftProjectFile:
    row = db_session.get(CraftProjectFile, file_id)
    if row is None or row.project_id != project_id or row.deleted:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "File not found")
    return row


def _project_usage(db_session: Session, project_id: UUID) -> tuple[int, int]:
    count, total = db_session.execute(
        select(
            func.count(CraftProjectFile.id),
            func.coalesce(func.sum(CraftProjectFile.size_bytes), 0),
        ).where(
            CraftProjectFile.project_id == project_id,
            CraftProjectFile.deleted.is_(False),
        )
    ).one()
    return int(count), int(total)


def upsert_project_file(
    db_session: Session,
    *,
    project_id: UUID,
    path: str,
    file_id: str,
    mime_type: str | None,
    size_bytes: int | None,
    content_hash: str | None,
    source: CraftProjectFileSource,
    produced_by_session_id: UUID | None = None,
) -> CraftProjectFile:
    clean_path = sanitize_project_path(path)
    existing = db_session.scalar(
        select(CraftProjectFile).where(
            CraftProjectFile.project_id == project_id,
            CraftProjectFile.path == clean_path,
        )
    )
    if existing is None:
        count, total = _project_usage(db_session, project_id)
        file_limit = project_file_limit(db_session, project_id)
        if count >= file_limit:
            raise OnyxError(
                OnyxErrorCode.INVALID_INPUT,
                "This project already has the maximum number of files",
            )
        added = size_bytes or 0
        if total + added > CRAFT_PROJECT_MAX_TOTAL_SIZE_BYTES:
            raise OnyxError(
                OnyxErrorCode.INVALID_INPUT,
                "This project is over the storage limit",
            )
        row = CraftProjectFile(
            project_id=project_id,
            path=clean_path,
            file_id=file_id,
            mime_type=mime_type,
            size_bytes=size_bytes,
            content_hash=content_hash,
            source=source,
            produced_by_session_id=produced_by_session_id,
        )
        db_session.add(row)
        db_session.flush()
        return row

    if existing.content_hash == content_hash and not existing.deleted:
        existing.produced_by_session_id = (
            produced_by_session_id or existing.produced_by_session_id
        )
        db_session.flush()
        return existing

    existing.file_id = file_id
    existing.mime_type = mime_type
    existing.size_bytes = size_bytes
    existing.content_hash = content_hash
    existing.source = source
    existing.produced_by_session_id = produced_by_session_id
    existing.version = existing.version + 1
    existing.deleted = False
    db_session.flush()
    return existing


def store_uploaded_project_file(
    db_session: Session,
    *,
    project: CraftProject,
    filename: str,
    content: bytes,
    content_type: str | None,
) -> CraftProjectFile:
    if len(content) > CRAFT_PROJECT_MAX_FILE_SIZE_BYTES:
        raise OnyxError(OnyxErrorCode.INVALID_INPUT, "File is too large")
    path = sanitize_project_path(filename)
    mime_type = content_type or mimetypes.guess_type(filename)[0]
    digest = hashlib.sha256(content).hexdigest()
    file_store = get_default_file_store()
    stored_id = file_store.save_file(
        content=BytesIO(content),
        display_name=path.rsplit("/", 1)[-1],
        file_origin=FileOrigin.CRAFT_PROJECT,
        file_type=mime_type or "application/octet-stream",
        file_metadata={
            "project_id": str(project.id),
            "path": path,
            "prefix": f"{CRAFT_PROJECT_STORE_PREFIX}/{project.id}",
        },
    )
    row = upsert_project_file(
        db_session,
        project_id=project.id,
        path=path,
        file_id=stored_id,
        mime_type=mime_type,
        size_bytes=len(content),
        content_hash=digest,
        source=CraftProjectFileSource.UPLOAD,
    )
    db_session.commit()
    db_session.refresh(row)
    return row


def replace_uploaded_project_file(
    db_session: Session,
    *,
    project: CraftProject,
    row: CraftProjectFile,
    content: bytes,
    content_type: str | None,
) -> CraftProjectFile:
    """Replace the stored bytes of an existing project file. Keep the same row."""
    if row.project_id != project.id or row.deleted:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "File not found")
    if len(content) > CRAFT_PROJECT_MAX_FILE_SIZE_BYTES:
        raise OnyxError(OnyxErrorCode.INVALID_INPUT, "File is too large")

    _, total = _project_usage(db_session, project.id)
    added = len(content) - (row.size_bytes or 0)
    if added > 0 and total + added > CRAFT_PROJECT_MAX_TOTAL_SIZE_BYTES:
        raise OnyxError(
            OnyxErrorCode.INVALID_INPUT,
            "This project is over the storage limit",
        )

    mime_type = content_type or row.mime_type or mimetypes.guess_type(row.path)[0]
    digest = hashlib.sha256(content).hexdigest()
    if row.content_hash == digest and not row.deleted:
        return row

    file_store = get_default_file_store()
    stored_id = file_store.save_file(
        content=BytesIO(content),
        display_name=row.path.rsplit("/", 1)[-1],
        file_origin=FileOrigin.CRAFT_PROJECT,
        file_type=mime_type or "application/octet-stream",
        file_metadata={
            "project_id": str(project.id),
            "path": row.path,
            "prefix": f"{CRAFT_PROJECT_STORE_PREFIX}/{project.id}",
        },
    )
    row.file_id = stored_id
    row.mime_type = mime_type
    row.size_bytes = len(content)
    row.content_hash = digest
    row.version = row.version + 1
    row.source = CraftProjectFileSource.UPLOAD
    db_session.commit()
    db_session.refresh(row)
    return row


def delete_project_file(db_session: Session, row: CraftProjectFile) -> None:
    row.deleted = True
    db_session.commit()


def count_project_sessions(db_session: Session, project_id: UUID) -> int:
    return int(
        db_session.scalar(
            select(func.count(BuildSession.id)).where(
                BuildSession.project_id == project_id
            )
        )
        or 0
    )


def list_project_sessions(db_session: Session, project_id: UUID) -> list[BuildSession]:
    return list(
        db_session.scalars(
            select(BuildSession)
            .where(BuildSession.project_id == project_id)
            .order_by(BuildSession.created_at.desc())
        )
    )


def build_project_fileset(db_session: Session, project_id: UUID) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    file_store = get_default_file_store()
    for row in list_project_files(db_session, project_id):
        rel = row.path.lstrip("/")
        try:
            files[rel] = file_store.read_file(row.file_id).read()
        except Exception:
            continue
    return files
