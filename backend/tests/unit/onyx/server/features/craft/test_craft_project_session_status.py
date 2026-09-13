from onyx.db.enums import BuildSessionStatus, CraftJobStatus
from onyx.server.features.craft_project.session_status import (
    project_session_activity_status,
)


def test_finished_job_is_idle_while_sandbox_stays_active() -> None:
    assert (
        project_session_activity_status(
            BuildSessionStatus.ACTIVE,
            job_status=CraftJobStatus.SUCCEEDED,
        )
        == BuildSessionStatus.IDLE
    )
    assert (
        project_session_activity_status(
            BuildSessionStatus.ACTIVE,
            job_status=CraftJobStatus.CANCELLED,
        )
        == BuildSessionStatus.IDLE
    )
    assert (
        project_session_activity_status(
            BuildSessionStatus.ACTIVE,
            job_status=None,
        )
        == BuildSessionStatus.IDLE
    )


def test_open_job_or_turn_is_active() -> None:
    assert (
        project_session_activity_status(
            BuildSessionStatus.ACTIVE,
            job_status=CraftJobStatus.WAITING_LANES,
        )
        == BuildSessionStatus.ACTIVE
    )
    assert (
        project_session_activity_status(
            BuildSessionStatus.IDLE,
            job_status=CraftJobStatus.SUCCEEDED,
            has_active_turn=True,
        )
        == BuildSessionStatus.ACTIVE
    )


def test_failed_job_or_sandbox_stays_failed() -> None:
    assert (
        project_session_activity_status(
            BuildSessionStatus.ACTIVE,
            job_status=CraftJobStatus.FAILED,
        )
        == BuildSessionStatus.FAILED
    )
    assert (
        project_session_activity_status(
            BuildSessionStatus.FAILED,
            job_status=CraftJobStatus.SUCCEEDED,
        )
        == BuildSessionStatus.FAILED
    )
    assert (
        project_session_activity_status(
            BuildSessionStatus.INITIALIZING,
            job_status=None,
        )
        == BuildSessionStatus.INITIALIZING
    )
