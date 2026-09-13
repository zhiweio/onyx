from uuid import uuid4

from sqlalchemy.orm import Session

from onyx.db.craft_job import create_craft_job, latest_job_statuses_for_sessions
from onyx.db.craft_project import (
    count_project_sessions,
    create_project,
    list_project_sessions,
)
from onyx.db.enums import (
    BuildSessionStatus,
    CraftJobStatus,
    SessionOrigin,
)
from onyx.db.models import BuildSession, User


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
    db_session.add_all([main, lane])
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
