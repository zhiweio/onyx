"""Persist session files to FileStore and remount them through a Craft Project."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from onyx.db.craft_project import (
    create_project,
    list_project_files,
    require_project_for_user,
    store_uploaded_project_file,
)
from onyx.db.models import BuildSession, User
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.file_store.file_store import get_default_file_store
from onyx.server.features.build.db.artifact import get_artifact_by_path
from onyx.server.features.build.sandbox.image.sandbox_daemon.contract import (
    OutputsManifestEntry,
    OutputsManifestResponse,
)
from onyx.server.features.build.session.artifact_persist import (
    persist_session_workspace_files,
    restore_archived_files_to_session,
)
from onyx.server.features.build.session.manager import SessionManager
from onyx.server.features.craft_project.runtime import write_project_to_session
from tests.common.craft.stubs import StubSandboxManager


class WorkspaceStub(StubSandboxManager):
    """In-memory session tree for persist / restore tests."""

    def __init__(self, files: dict[str, bytes]) -> None:
        super().__init__()
        self.files = dict(files)
        self.write_files_to_sandbox_silent = True
        self.write_sandbox_file_silent = True
        self.restored_files: dict[str, bytes] = {}
        self.list_directory_returns_by_path = {"attachments": []}
        self.outputs_manifest_returns = OutputsManifestResponse(
            entries=[
                OutputsManifestEntry(
                    path=path.removeprefix("outputs/"),
                    is_directory=False,
                    size=len(content),
                    sha256=None,
                )
                for path, content in files.items()
                if path.startswith("outputs/")
            ]
        )

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
    assert get_default_file_store().read_file(artifact.archive_file_id).read() == content

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

    stub = WorkspaceStub({"outputs/analysis.py": b"print('ok')"})
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
    assert "/analysis.py" in paths

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
    assert pushed["files"]["analysis.py"] == b"print('ok')"
    assert remount.last_write_sandbox_file_payload is not None
    assert "Project: Long tax task" in remount.last_write_sandbox_file_payload["content"]


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
