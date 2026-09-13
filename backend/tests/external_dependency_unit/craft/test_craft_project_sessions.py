from typing import Callable
from uuid import uuid4

from sqlalchemy.orm import Session

from onyx.configs.constants import MessageType
from onyx.db.craft_job import create_craft_job, latest_job_statuses_for_sessions
from onyx.db.craft_project import (
    count_project_sessions,
    create_project,
    list_project_sessions,
    list_snapshots_for_project,
    store_uploaded_project_file,
)
from onyx.db.enums import (
    BuildSessionStatus,
    CraftJobStatus,
    SandboxStatus,
    SessionOrigin,
)
from onyx.db.models import BuildMessage, BuildSession, Sandbox, Snapshot, User
from onyx.server.features.build.db.sandbox import get_sandbox_by_user_id
from onyx.server.features.build.sandbox.models import SandboxInfo, SnapshotResult
from onyx.server.features.build.session.manager import SessionManager
from tests.common.craft.stubs import StubSandboxManager


def test_project_lists_only_interactive_chats(
    db_session: Session, test_user: User
) -> None:
    project = create_project(db_session, user=test_user, name="Tax pack")
    main = BuildSession(
        id=uuid4(),
        user_id=test_user.id,
        name="Main chat",
        status=BuildSessionStatus.ACTIVE,
        origin=SessionOrigin.INTERACTIVE,
        project_id=project.id,
    )
    lane = BuildSession(
        id=uuid4(),
        user_id=test_user.id,
        name="Report / visualize-and-compose",
        status=BuildSessionStatus.ACTIVE,
        origin=SessionOrigin.JOB,
        project_id=project.id,
    )
    empty = BuildSession(
        id=uuid4(),
        user_id=test_user.id,
        name="Empty leftover",
        status=BuildSessionStatus.ACTIVE,
        origin=SessionOrigin.INTERACTIVE,
        project_id=project.id,
    )
    db_session.add_all([main, lane, empty])
    db_session.add(
        BuildMessage(
            session_id=main.id,
            turn_index=0,
            type=MessageType.ASSISTANT,
            message_metadata={
                "type": "agent_message",
                "content": {"type": "text", "text": "hello"},
            },
        )
    )
    db_session.commit()

    sessions = list_project_sessions(db_session, project.id)
    assert [row.id for row in sessions] == [main.id]
    assert count_project_sessions(db_session, project.id) == 1


def test_latest_job_status_uses_newest_row(
    db_session: Session, test_user: User
) -> None:
    project = create_project(db_session, user=test_user, name="Tax pack")
    session = BuildSession(
        id=uuid4(),
        user_id=test_user.id,
        name="Main chat",
        status=BuildSessionStatus.ACTIVE,
        origin=SessionOrigin.INTERACTIVE,
        project_id=project.id,
    )
    db_session.add(session)
    db_session.flush()
    cancelled = create_craft_job(
        db_session,
        user_id=test_user.id,
        session_id=session.id,
        name="first",
        domain="general",
        total_budget_seconds=60,
        phase_budget_seconds=30,
        project_id=project.id,
        phases=[{"id": "desk", "name": "Desk"}],
    )
    cancelled.status = CraftJobStatus.CANCELLED
    db_session.flush()
    succeeded = create_craft_job(
        db_session,
        user_id=test_user.id,
        session_id=session.id,
        name="second",
        domain="general",
        total_budget_seconds=60,
        phase_budget_seconds=30,
        project_id=project.id,
        phases=[{"id": "desk", "name": "Desk"}],
    )
    succeeded.status = CraftJobStatus.SUCCEEDED
    db_session.commit()

    statuses = latest_job_statuses_for_sessions(db_session, [session.id])
    assert statuses[session.id] == CraftJobStatus.SUCCEEDED


def test_reset_replaces_sandbox_and_migrates_project_chats(
    db_session: Session,
    test_user: User,
    sandbox: Callable[..., Sandbox],
    session_manager_with_stub: SessionManager,
    stub_sandbox_manager: StubSandboxManager,
) -> None:
    project = create_project(db_session, user=test_user, name="Tax pack")
    other = create_project(db_session, user=test_user, name="Other pack")
    store_uploaded_project_file(
        db_session,
        project=project,
        filename="rates.xlsx",
        content=b"abc",
        content_type="application/vnd.ms-excel",
    )
    old = sandbox(user=test_user, status=SandboxStatus.RUNNING)
    main = BuildSession(
        id=uuid4(),
        user_id=test_user.id,
        name="Main chat",
        status=BuildSessionStatus.IDLE,
        origin=SessionOrigin.INTERACTIVE,
        project_id=project.id,
    )
    other_session = BuildSession(
        id=uuid4(),
        user_id=test_user.id,
        name="Other chat",
        status=BuildSessionStatus.IDLE,
        origin=SessionOrigin.INTERACTIVE,
        project_id=other.id,
    )
    db_session.add_all([main, other_session])
    db_session.flush()
    project_snapshot = Snapshot(
        session_id=main.id,
        storage_path=f"sandbox-snapshots/test/{old.id}/project.tar.gz",
        size_bytes=12,
    )
    other_snapshot = Snapshot(
        session_id=other_session.id,
        storage_path=f"sandbox-snapshots/test/{old.id}/other.tar.gz",
        size_bytes=8,
    )
    db_session.add_all([project_snapshot, other_snapshot])
    db_session.commit()
    old_id = old.id
    main_id = main.id

    stub_sandbox_manager.provision_returns = SandboxInfo(
        sandbox_id=uuid4(),
        directory_path="/tmp/sandbox",
        status=SandboxStatus.RUNNING,
        last_heartbeat=None,
    )
    stub_sandbox_manager.terminate_silent = True
    stub_sandbox_manager.setup_session_workspace_silent = True
    stub_sandbox_manager.write_sandbox_file_silent = True
    stub_sandbox_manager.write_files_to_sandbox_silent = True

    new = session_manager_with_stub.reset_sandbox(
        test_user.id, project_id=project.id
    )

    assert new.id != old_id
    assert new.status == SandboxStatus.RUNNING
    assert new.user_id == test_user.id
    assert stub_sandbox_manager.terminate_count == 1
    assert stub_sandbox_manager.last_terminate_sandbox_id == old_id
    assert stub_sandbox_manager.last_provision_payload is not None
    assert stub_sandbox_manager.last_provision_payload["sandbox_id"] == new.id
    assert get_sandbox_by_user_id(db_session, test_user.id) is not None
    assert get_sandbox_by_user_id(db_session, test_user.id).id == new.id
    assert list_snapshots_for_project(db_session, project.id) == []
    leftover = list_snapshots_for_project(db_session, other.id)
    assert [row.session_id for row in leftover] == [other_session.id]
    assert stub_sandbox_manager.restore_snapshot_count == 0
    assert stub_sandbox_manager.setup_session_workspace_count == 1
    assert stub_sandbox_manager.last_setup_session_workspace_payload is not None
    assert stub_sandbox_manager.last_setup_session_workspace_payload["session_id"] == (
        main_id
    )
    assert stub_sandbox_manager.last_write_files_to_sandbox_payload is not None
    assert stub_sandbox_manager.last_write_files_to_sandbox_payload["mount_path"] == (
        f"/workspace/sessions/{main_id}/project"
    )
    assert stub_sandbox_manager.last_write_files_to_sandbox_payload["files"] == {
        "rates.xlsx": b"abc"
    }


def test_reset_can_migrate_all_sandbox_outputs(
    db_session: Session,
    test_user: User,
    sandbox: Callable[..., Sandbox],
    session_manager_with_stub: SessionManager,
    stub_sandbox_manager: StubSandboxManager,
) -> None:
    project = create_project(db_session, user=test_user, name="Tax pack")
    other = create_project(db_session, user=test_user, name="Other pack")
    old = sandbox(user=test_user, status=SandboxStatus.RUNNING)
    main = BuildSession(
        id=uuid4(),
        user_id=test_user.id,
        name="Main chat",
        status=BuildSessionStatus.IDLE,
        origin=SessionOrigin.INTERACTIVE,
        project_id=project.id,
    )
    other_session = BuildSession(
        id=uuid4(),
        user_id=test_user.id,
        name="Other chat",
        status=BuildSessionStatus.IDLE,
        origin=SessionOrigin.INTERACTIVE,
        project_id=other.id,
    )
    db_session.add_all([main, other_session])
    db_session.flush()
    project_snapshot = Snapshot(
        session_id=main.id,
        storage_path=f"sandbox-snapshots/test/{old.id}/project.tar.gz",
        size_bytes=12,
    )
    other_snapshot = Snapshot(
        session_id=other_session.id,
        storage_path=f"sandbox-snapshots/test/{old.id}/other.tar.gz",
        size_bytes=8,
    )
    db_session.add_all([project_snapshot, other_snapshot])
    db_session.commit()
    old_id = old.id
    main_id = main.id
    other_id = other_session.id

    stub_sandbox_manager.provision_returns = SandboxInfo(
        sandbox_id=uuid4(),
        directory_path="/tmp/sandbox",
        status=SandboxStatus.RUNNING,
        last_heartbeat=None,
    )
    stub_sandbox_manager.terminate_silent = True
    stub_sandbox_manager.setup_session_workspace_silent = True
    stub_sandbox_manager.restore_snapshot_silent = True
    stub_sandbox_manager.write_sandbox_file_silent = True
    stub_sandbox_manager.write_files_to_sandbox_silent = True
    stub_sandbox_manager.create_snapshot_returns = SnapshotResult(
        storage_path=f"sandbox-snapshots/test/{old_id}/extra.tar.gz",
        size_bytes=1,
    )
    stub_sandbox_manager.create_snapshot_results_by_session = {
        main_id: SnapshotResult(
            storage_path=f"sandbox-snapshots/test/{old_id}/{main_id}.tar.gz",
            size_bytes=16,
        ),
        other_id: SnapshotResult(
            storage_path=f"sandbox-snapshots/test/{old_id}/{other_id}.tar.gz",
            size_bytes=9,
        ),
    }

    new = session_manager_with_stub.reset_sandbox(
        test_user.id, project_id=project.id, migrate_outputs=True
    )

    assert new.id != old_id
    assert stub_sandbox_manager.create_snapshot_count >= 2
    assert stub_sandbox_manager.restore_snapshot_count >= 2
    assert stub_sandbox_manager.last_restore_snapshot_payload is not None
    assert stub_sandbox_manager.last_restore_snapshot_payload["sandbox_id"] == new.id
    assert stub_sandbox_manager.last_restore_snapshot_payload["session_id"] in {
        main_id,
        other_id,
    }
    leftover_project = list_snapshots_for_project(db_session, project.id)
    leftover_other = list_snapshots_for_project(db_session, other.id)
    assert [row.session_id for row in leftover_project] == [main_id]
    assert leftover_project[0].storage_path.endswith(f"{main_id}.tar.gz")
    assert [row.session_id for row in leftover_other] == [other_id]
