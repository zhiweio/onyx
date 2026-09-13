"""Persist session workspace trees into FileStore.

FileStore + Artifact rows are the content source of truth. The sandbox disk
is a cache. Fills ``artifact.archive_file_id`` so files survive sleep and
recycle. When the session belongs to a Craft Project, selected deliverables
are promoted.
"""

from __future__ import annotations

import hashlib
import mimetypes
from collections.abc import Callable
from io import BytesIO
from pathlib import PurePosixPath
from uuid import UUID

from sqlalchemy.orm import Session

from onyx.configs.constants import FileOrigin
from onyx.db.craft_project import retract_session_working_files, upsert_project_file
from onyx.db.enums import ArtifactType, CraftProjectFileSource
from onyx.db.models import Artifact, BuildSession
from onyx.file_store.file_store import get_default_file_store
from onyx.server.features.build.configs import (
    CRAFT_PROJECT_MAX_FILE_SIZE_BYTES,
    WORKSPACE_CATALOG_MAX_BYTES,
    WORKSPACE_CATALOG_MAX_FILES,
)
from onyx.server.features.build.db.artifact import (
    clear_pending_hydrate_for_session,
    get_session_artifacts,
    mark_artifact_deleted,
    set_artifact_archive_file_id,
    set_artifact_pending_hydrate,
    upsert_artifact,
)
from onyx.server.features.build.db.build_session import get_build_session
from onyx.server.features.build.jobs.durability import (
    is_durability_control_path,
    is_substantial_durability_text,
)
from onyx.server.features.build.sandbox.base import SandboxManager
from onyx.server.features.build.sandbox.models import FileSet, FilesystemEntry
from onyx.utils.logger import setup_logger

logger = setup_logger()

ATTACHMENTS_PREFIX = "__attachments__/"
PROJECT_PREFIX = "project/"
_SKIP_DIR_NAMES = {"node_modules", ".git", ".next", "__pycache__", ".venv"}
_SKIP_OUTPUT_ROOTS = {"web"}
_AUTO_PROMOTE_ROOTS = {"markdown", "pptx", "docx", "xlsx", "charts", "infographics"}
_AUTO_PROMOTE_SUFFIXES = {
    ".md",
    ".markdown",
    ".pptx",
    ".ppt",
    ".docx",
    ".doc",
    ".xlsx",
    ".xls",
    ".html",
    ".htm",
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
}
_NEVER_PROMOTE_ROOTS = {
    "research",
    "plan",
    "mcp",
    "commands",
    "extracted",
    "exceptions",
    "lanes",
    "web",
}

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


def validate_workspace_rel_path(path: str) -> str:
    """Return a normalized relative workspace path or raise ValueError."""
    cleaned = (path or "").replace("\\", "/").strip()
    if not cleaned or cleaned == ".":
        return ""
    if cleaned.startswith("/"):
        raise ValueError("absolute paths are not allowed")
    parts = [part for part in cleaned.split("/") if part and part != "."]
    if any(part == ".." for part in parts):
        raise ValueError("path traversal")
    return "/".join(parts)


def should_skip_output_path(path: str) -> bool:
    parts = PurePosixPath(path).parts
    if not parts:
        return True
    if parts[0] in _SKIP_OUTPUT_ROOTS:
        return True
    return any(part in _SKIP_DIR_NAMES for part in parts)


def should_auto_promote_output(catalog_path: str) -> bool:
    """Promote typed deliverables; keep research notes session-private."""
    if catalog_path.startswith(ATTACHMENTS_PREFIX):
        return False
    if catalog_path.startswith(PROJECT_PREFIX):
        return False
    if is_durability_control_path(catalog_path):
        return False
    if should_skip_output_path(catalog_path):
        return False
    parts = PurePosixPath(catalog_path).parts
    if not parts:
        return False
    if parts[0] in _NEVER_PROMOTE_ROOTS:
        return False
    if parts[0] in _AUTO_PROMOTE_ROOTS:
        return True
    return PurePosixPath(catalog_path).suffix.lower() in _AUTO_PROMOTE_SUFFIXES


def workspace_read_path(artifact_path: str) -> str:
    """Map a catalog path to a session-relative sandbox path."""
    if artifact_path.startswith(ATTACHMENTS_PREFIX):
        return f"attachments/{artifact_path[len(ATTACHMENTS_PREFIX) :]}"
    if artifact_path.startswith(PROJECT_PREFIX):
        return artifact_path
    return f"outputs/{artifact_path}"


def workspace_display_path(artifact_path: str) -> str:
    """Catalog path as the UI/API workspace path."""
    return workspace_read_path(artifact_path)


def catalog_paths_for_request(path: str) -> list[str]:
    """Candidate artifact.path values for a download request path."""
    clean = path.lstrip("/")
    candidates = [clean]
    if clean.startswith("outputs/"):
        candidates.append(clean[len("outputs/") :])
    elif clean.startswith("attachments/"):
        candidates.append(ATTACHMENTS_PREFIX + clean[len("attachments/") :])
    elif clean.startswith(PROJECT_PREFIX):
        candidates.append(clean)
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
    """Index and archive outputs/attachments/project. Best-effort; never raises."""
    persisted: list[Artifact] = []
    budget = _CatalogBudget()
    try:
        persisted.extend(
            _persist_outputs(
                db_session,
                sandbox_manager,
                sandbox_id=sandbox_id,
                session_id=session_id,
                turn_index=turn_index,
                budget=budget,
            )
        )
        persisted.extend(
            _persist_walked_tree(
                db_session,
                sandbox_manager,
                sandbox_id=sandbox_id,
                session_id=session_id,
                turn_index=turn_index,
                budget=budget,
                base_dir="attachments",
                catalog_for=lambda rel: f"{ATTACHMENTS_PREFIX}{rel}",
            )
        )
        persisted.extend(
            _persist_walked_tree(
                db_session,
                sandbox_manager,
                sandbox_id=sandbox_id,
                session_id=session_id,
                turn_index=turn_index,
                budget=budget,
                base_dir="project",
                catalog_for=lambda rel: f"{PROJECT_PREFIX}{rel}",
            )
        )
        session = get_build_session(session_id, user_id, db_session)
        if session is not None and session.project_id is not None:
            promote_session_outputs_to_project(db_session, session)
            _sync_project_tree_edits(db_session, session, persisted)
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
    if fileset:
        sandbox_manager.write_files_to_sandbox(
            sandbox_id=sandbox_id,
            mount_path=f"/workspace/sessions/{session_id}",
            files=fileset,
        )
    clear_pending_hydrate_for_session(db_session, session_id)


def archive_bytes_to_catalog(
    db_session: Session,
    *,
    session_id: UUID,
    catalog_path: str,
    name: str,
    content: bytes,
    turn_index: int | None = None,
    pending_hydrate: bool = False,
) -> Artifact | None:
    """Write bytes into FileStore and the session catalog without a sandbox."""
    if len(content) > CRAFT_PROJECT_MAX_FILE_SIZE_BYTES:
        return None
    digest = hashlib.sha256(content).hexdigest()
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
        if pending_hydrate:
            set_artifact_pending_hydrate(
                db_session,
                session_id=session_id,
                path=catalog_path,
                pending_hydrate=True,
            )
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
    if pending_hydrate:
        set_artifact_pending_hydrate(
            db_session,
            session_id=session_id,
            path=catalog_path,
            pending_hydrate=True,
        )
    return updated or artifact


def list_catalog_directory(
    db_session: Session,
    *,
    session_id: UUID,
    path: str,
) -> list[FilesystemEntry]:
    """List a workspace directory from archived catalog rows."""
    rel = validate_workspace_rel_path(path)
    prefix = f"{rel}/" if rel else ""
    dirs: dict[str, str] = {}
    files: list[FilesystemEntry] = []
    for artifact in get_session_artifacts(db_session, session_id=session_id):
        if not artifact.archive_file_id:
            continue
        display = workspace_display_path(artifact.path)
        if prefix:
            if not display.startswith(prefix):
                continue
            rest = display[len(prefix) :]
        else:
            rest = display
        if not rest:
            continue
        if "/" in rest:
            name = rest.split("/", 1)[0]
            child = f"{rel}/{name}" if rel else name
            dirs[name] = child
        else:
            files.append(
                FilesystemEntry(
                    name=rest,
                    path=display,
                    is_directory=False,
                    size=artifact.size_bytes,
                    mime_type=mimetypes.guess_type(rest)[0],
                )
            )
    entries = [
        FilesystemEntry(
            name=name,
            path=child_path,
            is_directory=True,
            size=None,
            mime_type=None,
        )
        for name, child_path in dirs.items()
    ]
    entries.extend(files)
    entries.sort(key=lambda entry: (not entry.is_directory, entry.name.lower()))
    return entries


def read_catalog_file(
    db_session: Session, *, session_id: UUID, path: str
) -> bytes | None:
    for candidate in catalog_paths_for_request(path):
        for artifact in get_session_artifacts(db_session, session_id=session_id):
            if artifact.path != candidate or not artifact.archive_file_id:
                continue
            try:
                return (
                    get_default_file_store().read_file(artifact.archive_file_id).read()
                )
            except Exception:
                logger.warning(
                    "Could not read archive for session %s path %s",
                    session_id,
                    candidate,
                )
    return None


def catalog_file_pairs(
    db_session: Session,
    *,
    session_id: UUID,
    path: str,
) -> list[tuple[str, bytes]]:
    """Return ``(arcname, bytes)`` for every catalog file under ``path``."""
    rel = validate_workspace_rel_path(path)
    prefix = f"{rel}/" if rel else ""
    pairs: list[tuple[str, bytes]] = []
    file_store = get_default_file_store()
    for artifact in get_session_artifacts(db_session, session_id=session_id):
        if not artifact.archive_file_id:
            continue
        display = workspace_display_path(artifact.path)
        if prefix and not display.startswith(prefix):
            continue
        if not prefix and display != rel and not display.startswith(f"{rel}/"):
            if rel:
                continue
        arcname = display[len(prefix) :] if prefix else display
        if not arcname or arcname.endswith("/"):
            continue
        try:
            pairs.append(
                (arcname, file_store.read_file(artifact.archive_file_id).read())
            )
        except Exception:
            continue
    return pairs


class _CatalogBudget:
    def __init__(self) -> None:
        self.files = 0
        self.bytes = 0

    def accept(self, size: int) -> bool:
        if self.files >= WORKSPACE_CATALOG_MAX_FILES:
            return False
        if self.bytes + size > WORKSPACE_CATALOG_MAX_BYTES:
            return False
        self.files += 1
        self.bytes += size
        return True


def _persist_outputs(
    db_session: Session,
    sandbox_manager: SandboxManager,
    *,
    sandbox_id: UUID,
    session_id: UUID,
    turn_index: int | None,
    budget: _CatalogBudget,
) -> list[Artifact]:
    try:
        manifest = sandbox_manager.get_outputs_manifest(sandbox_id, session_id)
    except Exception:
        logger.warning(
            "outputs manifest unavailable for session %s", session_id, exc_info=True
        )
        return []

    persisted: list[Artifact] = []
    for entry in manifest.entries:
        if entry.is_directory or should_skip_output_path(entry.path):
            continue
        size = entry.size if entry.size is not None else 0
        if size > CRAFT_PROJECT_MAX_FILE_SIZE_BYTES:
            continue
        if not budget.accept(size):
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
    return persisted


def _persist_walked_tree(
    db_session: Session,
    sandbox_manager: SandboxManager,
    *,
    sandbox_id: UUID,
    session_id: UUID,
    turn_index: int | None,
    budget: _CatalogBudget,
    base_dir: str,
    catalog_for: Callable[[str], str],
) -> list[Artifact]:
    persisted: list[Artifact] = []
    prefix = f"{base_dir}/"
    for workspace_path, name, size_bytes in _walk_files(
        sandbox_manager, sandbox_id, session_id, base_dir
    ):
        rel = (
            workspace_path[len(prefix) :] if workspace_path.startswith(prefix) else name
        )
        known_size = size_bytes if size_bytes is not None else 0
        if not budget.accept(known_size):
            continue
        artifact = _archive_one(
            db_session,
            sandbox_manager,
            sandbox_id=sandbox_id,
            session_id=session_id,
            catalog_path=catalog_for(rel),
            workspace_path=workspace_path,
            name=name,
            content_hash=None,
            size_bytes=size_bytes,
            turn_index=turn_index,
        )
        if artifact is not None:
            persisted.append(artifact)
    return persisted


def _walk_files(
    sandbox_manager: SandboxManager,
    sandbox_id: UUID,
    session_id: UUID,
    base_dir: str,
) -> list[tuple[str, str, int | None]]:
    collected: list[tuple[str, str, int | None]] = []

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
                collected.append((entry.path, entry.name, entry.size))

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
    if is_durability_control_path(catalog_path):
        try:
            preview = sandbox_manager.read_file(
                sandbox_id=sandbox_id, session_id=session_id, path=workspace_path
            )
        except Exception:
            return None
        text = (
            preview.decode("utf-8", errors="replace")
            if isinstance(preview, (bytes, bytearray))
            else ""
        )
        if not is_substantial_durability_text(text, catalog_path):
            mark_artifact_deleted(db_session, session_id=session_id, path=catalog_path)
            return None
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


def promote_session_outputs_to_project(
    db_session: Session,
    session: BuildSession,
) -> None:
    """Promote archived session deliverables into the bound Craft Project.

    Binding a finished session must reuse the catalog, not only files from
    the latest persist pass.
    """
    if session.project_id is None:
        return
    _promote_outputs_to_project(
        db_session,
        session,
        get_session_artifacts(db_session, session_id=session.id),
    )


def _promote_outputs_to_project(
    db_session: Session,
    session: BuildSession,
    artifacts: list[Artifact],
) -> None:
    project_id = session.project_id
    if project_id is None:
        return
    retract_session_working_files(db_session, project_id)
    for artifact in artifacts:
        if artifact.deleted or not artifact.archive_file_id:
            continue
        if not should_auto_promote_output(artifact.path):
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


def _sync_project_tree_edits(
    db_session: Session,
    session: BuildSession,
    artifacts: list[Artifact],
) -> None:
    project_id = session.project_id
    if project_id is None:
        return
    for artifact in artifacts:
        if not artifact.path.startswith(PROJECT_PREFIX):
            continue
        if artifact.deleted or not artifact.archive_file_id:
            continue
        rel = artifact.path[len(PROJECT_PREFIX) :]
        try:
            upsert_project_file(
                db_session,
                project_id=project_id,
                path=rel,
                file_id=artifact.archive_file_id,
                mime_type=mimetypes.guess_type(artifact.name)[0],
                size_bytes=artifact.size_bytes,
                content_hash=artifact.content_hash,
                source=CraftProjectFileSource.SESSION_OUTPUT,
                produced_by_session_id=session.id,
            )
        except Exception:
            logger.warning(
                "Could not sync project file %s into project %s",
                artifact.path,
                project_id,
                exc_info=True,
            )


def promote_workspace_path_to_project(
    db_session: Session,
    session: BuildSession,
    path: str,
) -> Artifact | None:
    """Promote one session catalog file into the bound Craft Project."""
    project_id = session.project_id
    if project_id is None:
        return None
    rel = validate_workspace_rel_path(path)
    from onyx.server.features.build.db.artifact import get_artifact_by_path

    artifact = None
    for candidate in catalog_paths_for_request(rel):
        artifact = get_artifact_by_path(
            db_session, session_id=session.id, path=candidate
        )
        if artifact is not None:
            break
    if artifact is None or not artifact.archive_file_id:
        return None
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
    db_session.commit()
    return artifact
