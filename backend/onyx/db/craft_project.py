"""Database operations for Craft Projects."""

from __future__ import annotations

import hashlib
import mimetypes
import re
from io import BytesIO
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from onyx.configs.constants import FileOrigin
from onyx.db.enums import CraftProjectFileSource
from onyx.db.models import BuildSession, CraftProject, CraftProjectFile, User
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

_PATH_SEGMENT = re.compile(r"[^A-Za-z0-9._\- ]+")


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
        cleaned = _PATH_SEGMENT.sub("", part).strip()
        if not cleaned or cleaned in {".", ".."}:
            continue
        parts.append(cleaned)
    if not parts:
        raise OnyxError(OnyxErrorCode.INVALID_INPUT, "Path is empty")
    return "/" + "/".join(parts)


def require_project_for_user(
    db_session: Session, project_id: UUID, user: User
) -> CraftProject:
    project = db_session.get(CraftProject, project_id)
    if project is None or project.user_id != user.id:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Project not found")
    return project


def list_projects_for_user(db_session: Session, user: User) -> list[CraftProject]:
    return list(
        db_session.scalars(
            select(CraftProject)
            .where(CraftProject.user_id == user.id)
            .order_by(CraftProject.updated_at.desc())
        )
    )


def create_project(
    db_session: Session,
    *,
    user: User,
    name: str,
    description: str = "",
    instructions: str | None = None,
) -> CraftProject:
    trimmed = name.strip()
    if not trimmed:
        raise OnyxError(OnyxErrorCode.INVALID_INPUT, "Name is required")
    project = CraftProject(
        user_id=user.id,
        name=trimmed[:128],
        description=description.strip(),
        instructions=instructions.strip() if instructions else None,
    )
    db_session.add(project)
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


def list_project_files(
    db_session: Session,
    project_id: UUID,
    *,
    include_deleted: bool = False,
) -> list[CraftProjectFile]:
    query = select(CraftProjectFile).where(CraftProjectFile.project_id == project_id)
    if not include_deleted:
        query = query.where(CraftProjectFile.deleted.is_(False))
    return list(db_session.scalars(query.order_by(CraftProjectFile.path)))


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
        file_metadata={"project_id": str(project.id), "path": path},
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


def list_project_sessions(
    db_session: Session, project_id: UUID
) -> list[BuildSession]:
    return list(
        db_session.scalars(
            select(BuildSession)
            .where(BuildSession.project_id == project_id)
            .order_by(BuildSession.created_at.desc())
        )
    )


def build_project_fileset(
    db_session: Session, project_id: UUID
) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    file_store = get_default_file_store()
    for row in list_project_files(db_session, project_id):
        rel = row.path.lstrip("/")
        try:
            files[rel] = file_store.read_file(row.file_id).read()
        except Exception:
            continue
    return files
