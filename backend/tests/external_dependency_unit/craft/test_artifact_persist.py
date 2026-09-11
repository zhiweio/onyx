"""Persist session files to FileStore and remount them through a Craft Project."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from onyx.db.craft_project import (
    create_project,
    list_project_files,
    list_projects_for_user,
    require_project_for_user,
    require_project_write_for_user,
    store_uploaded_project_file,
    upsert_project_file,
)
from onyx.db.enums import CraftProjectFileSource, SandboxStatus
from onyx.db.models import BuildSession, User
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.file_store.file_store import get_default_file_store
from onyx.server.features.build.db.artifact import get_artifact_by_path
from onyx.server.features.build.jobs.durability import (
    SEED_MEMORY_MD,
    SEED_PLAN_MD,
    SEED_TODO_MD,
)
from onyx.server.features.build.sandbox.image.sandbox_daemon.contract import (
    OutputsManifestEntry,
    OutputsManifestResponse,
)
from onyx.server.features.build.sandbox.models import FilesystemEntry
from onyx.server.features.build.session.artifact_persist import (
    archive_bytes_to_catalog,
    persist_session_workspace_files,
    promote_workspace_path_to_project,
    restore_archived_files_to_session,
)
from onyx.server.features.build.session.manager import SessionManager
from onyx.server.features.craft_project.runtime import (
    project_has_workspace_brief,
    write_project_to_session,
)
from tests.common.craft.stubs import StubSandboxManager
from tests.external_dependency_unit.craft.db_helpers import (
    add_user_to_group,
    make_group,
)


class WorkspaceStub(StubSandboxManager):
    """In-memory session tree for persist / restore tests."""

    def __init__(self, files: dict[str, bytes]) -> None:
        super().__init__()
        self.files = dict(files)
        self.write_files_to_sandbox_silent = True
        self.write_sandbox_file_silent = True
        self.restored_files: dict[str, bytes] = {}
        self.get_upload_stats_returns = (0, 0)
        self.upload_file_returns = ""
        self.outputs_manifest_returns = OutputsManifestResponse(
            entries=[
                OutputsManifestEntry(
                    path=path.removeprefix("outputs/"),
                    is_directory=False,
                    size=len(content),
                    sha256=hashlib.sha256(content).hexdigest(),
                )
                for path, content in files.items()
                if path.startswith("outputs/")
            ]
        )

    def list_directory(
        self, sandbox_id: UUID, session_id: UUID, path: str
    ) -> list[FilesystemEntry]:
        del sandbox_id, session_id
        prefix = path.rstrip("/")
        children: dict[str, FilesystemEntry] = {}
        for file_path, content in self.files.items():
            if prefix:
                if file_path == prefix:
                    continue
                if not file_path.startswith(prefix + "/"):
                    continue
                rest = file_path[len(prefix) + 1 :]
            else:
                rest = file_path
            name = rest.split("/", 1)[0]
            is_directory = "/" in rest
            child_path = f"{prefix}/{name}" if prefix else name
            if name not in children:
                children[name] = FilesystemEntry(
                    name=name,
                    path=child_path,
                    is_directory=is_directory,
                    size=None if is_directory else len(content),
                    mime_type=None,
                )
        return list(children.values())

    def upload_file(
        self,
        sandbox_id: UUID,
        session_id: UUID,
        filename: str,
        content: bytes,
    ) -> str:
        del sandbox_id, session_id
        relative = f"attachments/{filename}"
        self.files[relative] = content
        self.upload_file_returns = relative
        return relative

    def read_file(self, sandbox_id: UUID, session_id: UUID, path: str) -> bytes:
        del sandbox_id, session_id
        if path not in self.files:
            raise ValueError(f"File not found: {path}")
        return self.files[path]

    def write_files_to_sandbox(
        self,
        *,
        sandbox_id: UUID,
        mount_path: str,
        files: dict[str, bytes],
    ) -> None:
        super().write_files_to_sandbox(
            sandbox_id=sandbox_id, mount_path=mount_path, files=files
        )
        self.restored_files = dict(files)


def test_persist_survives_sandbox_recycle(
    db_session: Session,
    tenant_context: None,  # noqa: ARG001
    test_user: User,
    build_session_with_user: Callable[..., BuildSession],
    initialize_file_store: None,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = build_session_with_user(provision_sandbox=True)
    content = b"PK\x03\x04docx-bytes"
    stub = WorkspaceStub({"outputs/board.docx": content})

    persist_session_workspace_files(
        db_session,
        stub,
        sandbox_id=uuid4(),
        session_id=session.id,
        user_id=test_user.id,
        turn_index=1,
    )

    artifact = get_artifact_by_path(
        db_session, session_id=session.id, path="board.docx"
    )
    assert artifact is not None
    assert artifact.archive_file_id
    assert (
        get_default_file_store().read_file(artifact.archive_file_id).read() == content
    )

    gone = WorkspaceStub({})
    monkeypatch.setattr(
        "onyx.server.features.build.session.manager.get_sandbox_manager",
        lambda: gone,
    )
    manager = SessionManager(db_session)
    downloaded = manager.download_artifact(
        session.id, test_user.id, "outputs/board.docx"
    )
    assert downloaded is not None
    body, _mime, filename = downloaded
    assert filename == "board.docx"
    assert body == content

    restore_archived_files_to_session(
        db_session,
        gone,
        sandbox_id=uuid4(),
        session_id=session.id,
    )
    assert gone.restored_files["outputs/board.docx"] == content


def test_project_remounts_upload_and_session_output(
    db_session: Session,
    tenant_context: None,  # noqa: ARG001
    test_user: User,
    build_session_with_user: Callable[..., BuildSession],
    initialize_file_store: None,  # noqa: ARG001
) -> None:
    project = create_project(db_session, user=test_user, name="Long tax task")
    store_uploaded_project_file(
        db_session,
        project=project,
        filename="rates.xlsx",
        content=b"xlsx-shared",
        content_type="application/vnd.ms-excel",
    )

    session_one = build_session_with_user()
    session_one.project_id = project.id
    db_session.commit()

    stub = WorkspaceStub({"outputs/markdown/report.md": b"# report"})
    persist_session_workspace_files(
        db_session,
        stub,
        sandbox_id=uuid4(),
        session_id=session_one.id,
        user_id=test_user.id,
        turn_index=1,
    )

    paths = {row.path for row in list_project_files(db_session, project.id)}
    assert "/rates.xlsx" in paths
    assert "/markdown/report.md" in paths

    session_two = build_session_with_user()
    remount = WorkspaceStub({})
    write_project_to_session(
        db_session,
        remount,
        uuid4(),
        session_two.id,
        project.id,
        test_user,
    )
    pushed = remount.last_write_files_to_sandbox_payload
    assert pushed is not None
    assert pushed["files"]["rates.xlsx"] == b"xlsx-shared"
    assert pushed["files"]["markdown/report.md"] == b"# report"
    assert remount.last_write_sandbox_file_payload is not None
    assert (
        "Project: Long tax task" in remount.last_write_sandbox_file_payload["content"]
    )


def test_other_user_cannot_see_project(
    db_session: Session,
    tenant_context: None,  # noqa: ARG001
    test_user: User,
) -> None:
    from tests.external_dependency_unit.conftest import create_test_user

    project = create_project(db_session, user=test_user, name="Owner only")
    other = create_test_user(db_session, "craft-proj-other")
    with pytest.raises(OnyxError) as exc:
        require_project_for_user(db_session, project.id, other)
    assert exc.value.error_code == OnyxErrorCode.NOT_FOUND


def test_research_tree_stays_session_private_until_promoted(
    db_session: Session,
    tenant_context: None,  # noqa: ARG001
    test_user: User,
    build_session_with_user: Callable[..., BuildSession],
    initialize_file_store: None,  # noqa: ARG001
) -> None:
    project = create_project(db_session, user=test_user, name="Biomed")
    session_a = build_session_with_user()
    session_a.project_id = project.id
    db_session.commit()

    stub = WorkspaceStub(
        {
            "outputs/research/a.md": b"notes",
            "outputs/markdown/brief.md": b"# brief",
        }
    )
    persist_session_workspace_files(
        db_session,
        stub,
        sandbox_id=uuid4(),
        session_id=session_a.id,
        user_id=test_user.id,
        turn_index=1,
    )
    paths = {row.path for row in list_project_files(db_session, project.id)}
    assert "/markdown/brief.md" in paths
    assert "/research/a.md" not in paths

    artifact = get_artifact_by_path(
        db_session, session_id=session_a.id, path="research/a.md"
    )
    assert artifact is not None
    promote_workspace_path_to_project(db_session, session_a, "outputs/research/a.md")
    paths = {row.path for row in list_project_files(db_session, project.id)}
    assert "/research/a.md" in paths

    session_b = build_session_with_user()
    remount = WorkspaceStub({})
    write_project_to_session(
        db_session, remount, uuid4(), session_b.id, project.id, test_user
    )
    pushed = remount.last_write_files_to_sandbox_payload
    assert pushed is not None
    assert "research/a.md" in pushed["files"]
    assert "markdown/brief.md" in pushed["files"]


def test_seed_plan_files_are_not_promoted_or_cataloged(
    db_session: Session,
    tenant_context: None,  # noqa: ARG001
    test_user: User,
    build_session_with_user: Callable[..., BuildSession],
    initialize_file_store: None,  # noqa: ARG001
) -> None:
    project = create_project(db_session, user=test_user, name="HMPL stub")
    upsert_project_file(
        db_session,
        project_id=project.id,
        path="PLAN.md",
        file_id="stale-plan",
        mime_type="text/markdown",
        size_bytes=7,
        content_hash="abc",
        source=CraftProjectFileSource.SESSION_OUTPUT,
    )
    db_session.commit()

    session = build_session_with_user()
    session.project_id = project.id
    db_session.commit()

    stub = WorkspaceStub(
        {
            "outputs/PLAN.md": SEED_PLAN_MD.encode(),
            "outputs/TODO.md": SEED_TODO_MD.encode(),
            "outputs/MEMORY.md": SEED_MEMORY_MD.encode(),
            "outputs/markdown/report.md": b"# report\n",
        }
    )
    persist_session_workspace_files(
        db_session,
        stub,
        sandbox_id=uuid4(),
        session_id=session.id,
        user_id=test_user.id,
        turn_index=1,
    )

    paths = {row.path for row in list_project_files(db_session, project.id)}
    assert "/markdown/report.md" in paths
    assert "/PLAN.md" not in paths
    assert "/TODO.md" not in paths
    assert "/MEMORY.md" not in paths

    for catalog_path in ("PLAN.md", "TODO.md", "MEMORY.md"):
        artifact = get_artifact_by_path(
            db_session, session_id=session.id, path=catalog_path
        )
        assert artifact is None or artifact.deleted is True
    report = get_artifact_by_path(
        db_session, session_id=session.id, path="markdown/report.md"
    )
    assert report is not None
    assert report.deleted is False


def test_unchanged_hash_skips_filestore_write(
    db_session: Session,
    tenant_context: None,  # noqa: ARG001
    test_user: User,
    build_session_with_user: Callable[..., BuildSession],
    initialize_file_store: None,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = build_session_with_user()
    content = b"stable-research"
    stub = WorkspaceStub({"outputs/research/a.md": content})
    persist_session_workspace_files(
        db_session,
        stub,
        sandbox_id=uuid4(),
        session_id=session.id,
        user_id=test_user.id,
        turn_index=1,
    )
    artifact = get_artifact_by_path(
        db_session, session_id=session.id, path="research/a.md"
    )
    assert artifact is not None
    first_id = artifact.archive_file_id
    assert first_id

    store = get_default_file_store()
    writes = {"n": 0}
    original = store.save_file

    def _count_save(*args: object, **kwargs: object) -> str:
        writes["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(store, "save_file", _count_save)
    persist_session_workspace_files(
        db_session,
        stub,
        sandbox_id=uuid4(),
        session_id=session.id,
        user_id=test_user.id,
        turn_index=2,
    )
    assert writes["n"] == 0
    again = get_artifact_by_path(
        db_session, session_id=session.id, path="research/a.md"
    )
    assert again is not None
    assert again.archive_file_id == first_id


def test_large_tree_archives_past_two_hundred_files(
    db_session: Session,
    tenant_context: None,  # noqa: ARG001
    test_user: User,
    build_session_with_user: Callable[..., BuildSession],
    initialize_file_store: None,  # noqa: ARG001
) -> None:
    session = build_session_with_user()
    files = {f"outputs/research/n{i:03d}.md": f"note-{i}".encode() for i in range(210)}
    stub = WorkspaceStub(files)
    persist_session_workspace_files(
        db_session,
        stub,
        sandbox_id=uuid4(),
        session_id=session.id,
        user_id=test_user.id,
        turn_index=1,
    )
    for i in (0, 199, 209):
        artifact = get_artifact_by_path(
            db_session,
            session_id=session.id,
            path=f"research/n{i:03d}.md",
        )
        assert artifact is not None
        assert artifact.archive_file_id


def test_sleeping_sandbox_uses_catalog_and_pending_hydrate(
    db_session: Session,
    tenant_context: None,  # noqa: ARG001
    test_user: User,
    build_session_with_user: Callable[..., BuildSession],
    sandbox: Callable[..., object],
    initialize_file_store: None,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sandbox(status=SandboxStatus.SLEEPING)
    session = build_session_with_user(provision_sandbox=False)
    archive_bytes_to_catalog(
        db_session,
        session_id=session.id,
        catalog_path="research/a.md",
        name="a.md",
        content=b"asleep-notes",
    )
    db_session.commit()

    stub = WorkspaceStub({})
    monkeypatch.setattr(
        "onyx.server.features.build.session.manager.get_sandbox_manager",
        lambda: stub,
    )
    manager = SessionManager(db_session)
    listing = manager.list_directory(session.id, test_user.id, "outputs/research")
    assert listing is not None
    names = {entry.name for entry in listing.entries}
    assert "a.md" in names

    downloaded = manager.download_artifact(
        session.id, test_user.id, "outputs/research/a.md"
    )
    assert downloaded is not None
    assert downloaded[0] == b"asleep-notes"

    relative, size = manager.upload_file(
        session.id, test_user.id, "brief.pdf", b"pdf-bytes"
    )
    assert relative == "attachments/brief.pdf"
    assert size == len(b"pdf-bytes")
    uploaded = get_artifact_by_path(
        db_session, session_id=session.id, path="__attachments__/brief.pdf"
    )
    assert uploaded is not None
    assert uploaded.pending_hydrate is True
    assert stub.upload_file_count == 0

    restore_archived_files_to_session(
        db_session,
        stub,
        sandbox_id=uuid4(),
        session_id=session.id,
    )
    assert stub.restored_files["outputs/research/a.md"] == b"asleep-notes"
    assert stub.restored_files["attachments/brief.pdf"] == b"pdf-bytes"
    db_session.refresh(uploaded)
    assert uploaded.pending_hydrate is False


def test_workspace_paths_reject_traversal(
    db_session: Session,
    tenant_context: None,  # noqa: ARG001
    test_user: User,
    build_session_with_user: Callable[..., BuildSession],
    sandbox: Callable[..., object],
    initialize_file_store: None,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sandbox(status=SandboxStatus.SLEEPING)
    session = build_session_with_user()
    stub = WorkspaceStub({})
    monkeypatch.setattr(
        "onyx.server.features.build.session.manager.get_sandbox_manager",
        lambda: stub,
    )
    manager = SessionManager(db_session)
    with pytest.raises(ValueError, match="path traversal"):
        manager.list_directory(session.id, test_user.id, "../etc")
    with pytest.raises(ValueError, match="absolute"):
        manager.download_artifact(session.id, test_user.id, "/etc/passwd")
    with pytest.raises(ValueError, match="path traversal"):
        manager.upload_file(session.id, test_user.id, "../x.pdf", b"x")


def test_empty_project_does_not_seed_workspace_files(
    db_session: Session,
    tenant_context: None,  # noqa: ARG001
    test_user: User,
) -> None:
    project = create_project(db_session, user=test_user, name="Scratch")
    remount = WorkspaceStub({})
    write_project_to_session(
        db_session, remount, uuid4(), uuid4(), project.id, test_user
    )
    assert remount.write_sandbox_file_count == 0
    assert remount.last_write_files_to_sandbox_payload is None
    assert not project_has_workspace_brief(
        description="",
        instructions=None,
        file_names=[],
    )


def test_group_member_can_read_team_project(
    db_session: Session,
    tenant_context: None,  # noqa: ARG001
    test_user: User,
) -> None:
    from tests.external_dependency_unit.conftest import create_test_user

    group = make_group(db_session)
    add_user_to_group(db_session, test_user, group)
    project = create_project(
        db_session,
        user=test_user,
        name="Team workspace",
        user_group_id=group.id,
    )
    member = create_test_user(db_session, "craft-team-member")
    add_user_to_group(db_session, member, group)
    outsider = create_test_user(db_session, "craft-team-outsider")
    db_session.commit()

    assert require_project_for_user(db_session, project.id, member).id == project.id
    assert project.id in {row.id for row in list_projects_for_user(db_session, member)}
    with pytest.raises(OnyxError) as write_exc:
        require_project_write_for_user(db_session, project.id, member)
    assert write_exc.value.error_code == OnyxErrorCode.NOT_FOUND
    with pytest.raises(OnyxError) as read_exc:
        require_project_for_user(db_session, project.id, outsider)
    assert read_exc.value.error_code == OnyxErrorCode.NOT_FOUND
