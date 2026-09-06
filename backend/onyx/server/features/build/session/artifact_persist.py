"""Persist session outputs and attachments into FileStore.

Fills ``artifact.archive_file_id`` so files survive sandbox recycle.
When the session belongs to a Craft Project, new outputs are promoted.
"""

from __future__ import annotations

import hashlib
import mimetypes
from io import BytesIO
from pathlib import PurePosixPath
from uuid import UUID

from sqlalchemy.orm import Session

from onyx.configs.constants import FileOrigin
from onyx.db.craft_project import upsert_project_file
from onyx.db.enums import ArtifactType, CraftProjectFileSource
from onyx.db.models import Artifact, BuildSession
from onyx.file_store.file_store import get_default_file_store
from onyx.server.features.build.configs import CRAFT_PROJECT_MAX_FILE_SIZE_BYTES
from onyx.server.features.build.db.artifact import (
    get_session_artifacts,
    set_artifact_archive_file_id,
    upsert_artifact,
)
from onyx.server.features.build.db.build_session import get_build_session
from onyx.server.features.build.sandbox.base import SandboxManager
from onyx.server.features.build.sandbox.models import FileSet, FilesystemEntry
from onyx.utils.logger import setup_logger

logger = setup_logger()

ATTACHMENTS_PREFIX = "__attachments__/"
MAX_FILES_PER_PERSIST = 200
_SKIP_DIR_NAMES = {"node_modules", ".git", ".next", "__pycache__"}

_EXT_TO_TYPE: dict[str, ArtifactType] = {
    ".pptx": ArtifactType.PPTX,
    ".ppt": ArtifactType.PPTX,
    ".docx": ArtifactType.DOCX,
    ".doc": ArtifactType.DOCX,
    ".xlsx": ArtifactType.EXCEL,
    ".xls": ArtifactType.EXCEL,
    ".csv": ArtifactType.CSV,
    ".md": ArtifactType.MARKDOWN,
    ".markdown": ArtifactType.MARKDOWN,
    ".pdf": ArtifactType.PDF,
    ".png": ArtifactType.IMAGE,
    ".jpg": ArtifactType.IMAGE,
    ".jpeg": ArtifactType.IMAGE,
    ".gif": ArtifactType.IMAGE,
    ".webp": ArtifactType.IMAGE,
    ".svg": ArtifactType.IMAGE,
    ".py": ArtifactType.CODE,
    ".ts": ArtifactType.CODE,
    ".tsx": ArtifactType.CODE,
    ".js": ArtifactType.CODE,
    ".json": ArtifactType.CODE,
    ".html": ArtifactType.CODE,
    ".css": ArtifactType.CODE,
    ".zip": ArtifactType.ARCHIVE,
    ".tar": ArtifactType.ARCHIVE,
    ".gz": ArtifactType.ARCHIVE,
}


def infer_artifact_type(name: str) -> ArtifactType:
    return _EXT_TO_TYPE.get(PurePosixPath(name).suffix.lower(), ArtifactType.FILE)


def should_skip_output_path(path: str) -> bool:
    parts = PurePosixPath(path).parts
    if not parts:
        return True
    if parts[0] == "web":
        return True
    return any(part in _SKIP_DIR_NAMES for part in parts)


def workspace_read_path(artifact_path: str) -> str:
    """Map a catalog path to a session-relative sandbox path."""
    if artifact_path.startswith(ATTACHMENTS_PREFIX):
        return f"attachments/{artifact_path[len(ATTACHMENTS_PREFIX) :]}"
    return f"outputs/{artifact_path}"


def catalog_paths_for_request(path: str) -> list[str]:
    """Candidate artifact.path values for a download request path."""
    clean = path.lstrip("/")
    candidates = [clean]
    if clean.startswith("outputs/"):
        candidates.append(clean[len("outputs/") :])
    elif clean.startswith("attachments/"):
        candidates.append(ATTACHMENTS_PREFIX + clean[len("attachments/") :])
    else:
        candidates.append(ATTACHMENTS_PREFIX + clean)
    return candidates


def persist_session_workspace_files(
    db_session: Session,
    sandbox_manager: SandboxManager,
    *,
    sandbox_id: UUID,
    session_id: UUID,
    user_id: UUID,
    turn_index: int | None = None,
) -> list[Artifact]:
    """Index and archive outputs/attachments. Best-effort; never raises."""
    persisted: list[Artifact] = []
    try:
        persisted.extend(
            _persist_outputs(
                db_session,
                sandbox_manager,
                sandbox_id=sandbox_id,
                session_id=session_id,
                turn_index=turn_index,
            )
        )
        persisted.extend(
            _persist_attachments(
                db_session,
                sandbox_manager,
                sandbox_id=sandbox_id,
                session_id=session_id,
                turn_index=turn_index,
            )
        )
        session = get_build_session(session_id, user_id, db_session)
        if session is not None and session.project_id is not None:
            _promote_outputs_to_project(db_session, session, persisted)
        db_session.commit()
    except Exception:
        logger.exception("Failed to persist files for session %s", session_id)
        try:
            db_session.rollback()
        except Exception:
            pass
    return persisted


def restore_archived_files_to_session(
    db_session: Session,
    sandbox_manager: SandboxManager,
    *,
    sandbox_id: UUID,
    session_id: UUID,
) -> None:
    """Write archived blobs back into the session workspace."""
    fileset: FileSet = {}
    file_store = get_default_file_store()
    for artifact in get_session_artifacts(db_session, session_id=session_id):
        if not artifact.archive_file_id:
            continue
        try:
            fileset[workspace_read_path(artifact.path)] = file_store.read_file(
                artifact.archive_file_id
            ).read()
        except Exception:
            logger.warning(
                "Could not read archive %s for session %s path %s",
                artifact.archive_file_id,
                session_id,
                artifact.path,
            )
    if not fileset:
        return
    sandbox_manager.write_files_to_sandbox(
        sandbox_id=sandbox_id,
        mount_path=f"/workspace/sessions/{session_id}",
        files=fileset,
    )


def _persist_outputs(
    db_session: Session,
    sandbox_manager: SandboxManager,
    *,
    sandbox_id: UUID,
    session_id: UUID,
    turn_index: int | None,
) -> list[Artifact]:
    try:
        manifest = sandbox_manager.get_outputs_manifest(sandbox_id, session_id)
    except Exception:
        logger.warning(
            "outputs manifest unavailable for session %s", session_id, exc_info=True
        )
        return []

    persisted: list[Artifact] = []
    count = 0
    for entry in manifest.entries:
        if entry.is_directory or should_skip_output_path(entry.path):
            continue
        if count >= MAX_FILES_PER_PERSIST:
            break
        if entry.size is not None and entry.size > CRAFT_PROJECT_MAX_FILE_SIZE_BYTES:
            continue
        artifact = _archive_one(
            db_session,
            sandbox_manager,
            sandbox_id=sandbox_id,
            session_id=session_id,
            catalog_path=entry.path,
            workspace_path=f"outputs/{entry.path}",
            name=PurePosixPath(entry.path).name,
            content_hash=entry.sha256,
            size_bytes=entry.size,
            turn_index=turn_index,
        )
        if artifact is not None:
            persisted.append(artifact)
            count += 1
    return persisted


def _persist_attachments(
    db_session: Session,
    sandbox_manager: SandboxManager,
    *,
    sandbox_id: UUID,
    session_id: UUID,
    turn_index: int | None,
) -> list[Artifact]:
    persisted: list[Artifact] = []
    count = 0
    for workspace_path, name in _walk_files(
        sandbox_manager, sandbox_id, session_id, "attachments"
    ):
        if count >= MAX_FILES_PER_PERSIST:
            break
        rel = (
            workspace_path[len("attachments/") :]
            if workspace_path.startswith("attachments/")
            else name
        )
        artifact = _archive_one(
            db_session,
            sandbox_manager,
            sandbox_id=sandbox_id,
            session_id=session_id,
            catalog_path=f"{ATTACHMENTS_PREFIX}{rel}",
            workspace_path=workspace_path,
            name=name,
            content_hash=None,
            size_bytes=None,
            turn_index=turn_index,
        )
        if artifact is not None:
            persisted.append(artifact)
            count += 1
    return persisted


def _walk_files(
    sandbox_manager: SandboxManager,
    sandbox_id: UUID,
    session_id: UUID,
    base_dir: str,
) -> list[tuple[str, str]]:
    collected: list[tuple[str, str]] = []

    def walk(dir_path: str) -> None:
        try:
            entries: list[FilesystemEntry] = sandbox_manager.list_directory(
                sandbox_id=sandbox_id, session_id=session_id, path=dir_path
            )
        except ValueError:
            return
        except Exception:
            logger.warning("Could not list %s for session %s", dir_path, session_id)
            return
        for entry in entries:
            if entry.name.startswith(".") or entry.name in _SKIP_DIR_NAMES:
                continue
            if entry.is_directory:
                walk(entry.path)
            else:
                collected.append((entry.path, entry.name))

    walk(base_dir)
    return collected


def _archive_one(
    db_session: Session,
    sandbox_manager: SandboxManager,
    *,
    sandbox_id: UUID,
    session_id: UUID,
    catalog_path: str,
    workspace_path: str,
    name: str,
    content_hash: str | None,
    size_bytes: int | None,
    turn_index: int | None,
) -> Artifact | None:
    artifact = upsert_artifact(
        db_session,
        session_id=session_id,
        artifact_type=infer_artifact_type(name),
        path=catalog_path,
        name=name,
        turn_index=turn_index,
        size_bytes=size_bytes,
        content_hash=content_hash,
    )
    if (
        artifact.archive_file_id
        and content_hash
        and artifact.content_hash == content_hash
    ):
        return artifact
    try:
        content = sandbox_manager.read_file(
            sandbox_id=sandbox_id, session_id=session_id, path=workspace_path
        )
    except Exception:
        logger.warning("Could not read %s for session %s", workspace_path, session_id)
        return artifact
    if len(content) > CRAFT_PROJECT_MAX_FILE_SIZE_BYTES:
        return artifact
    digest = content_hash or hashlib.sha256(content).hexdigest()
    if artifact.content_hash != digest:
        artifact = upsert_artifact(
            db_session,
            session_id=session_id,
            artifact_type=infer_artifact_type(name),
            path=catalog_path,
            name=name,
            turn_index=turn_index,
            size_bytes=len(content),
            content_hash=digest,
        )
    if artifact.archive_file_id and artifact.content_hash == digest:
        return artifact
    mime_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
    stored_id = get_default_file_store().save_file(
        content=BytesIO(content),
        display_name=name,
        file_origin=FileOrigin.CRAFT_ARTIFACT,
        file_type=mime_type,
        file_metadata={"session_id": str(session_id), "path": catalog_path},
    )
    updated = set_artifact_archive_file_id(
        db_session,
        session_id=session_id,
        path=catalog_path,
        archive_file_id=stored_id,
    )
    return updated or artifact


def _promote_outputs_to_project(
    db_session: Session,
    session: BuildSession,
    artifacts: list[Artifact],
) -> None:
    project_id = session.project_id
    if project_id is None:
        return
    for artifact in artifacts:
        if artifact.deleted or not artifact.archive_file_id:
            continue
        if artifact.path.startswith(ATTACHMENTS_PREFIX):
            continue
        if should_skip_output_path(artifact.path):
            continue
        try:
            upsert_project_file(
                db_session,
                project_id=project_id,
                path=artifact.path,
                file_id=artifact.archive_file_id,
                mime_type=mimetypes.guess_type(artifact.name)[0],
                size_bytes=artifact.size_bytes,
                content_hash=artifact.content_hash,
                source=CraftProjectFileSource.SESSION_OUTPUT,
                produced_by_session_id=session.id,
            )
        except Exception:
            logger.warning(
                "Could not promote %s into project %s",
                artifact.path,
                project_id,
                exc_info=True,
            )
