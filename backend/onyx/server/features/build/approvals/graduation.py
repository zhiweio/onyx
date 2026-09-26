"""Ship-gate graduation: supervised approvals promote a task's pre-approval.

The QM discipline, adapted to scheduled tasks. A RUNNING task run parks on an
ASK-gated request; every human approval counts one supervised pass for the
(task, target) pair. After ``CRAFT_ACTION_GRADUATION_THRESHOLD`` consecutive
passes the task's pre-approval for that target is created automatically, bound
to the current policy version — that grant row IS the graduated "auto" state.

Reset rules (both void progress, never silently accumulate):
- a human REJECTION deletes the counter;
- a policy edit bumps ``GatedApp.policy_version``, which voids the counter
  (version mismatch) and the graduated grant alike.
"""

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from onyx.configs.constants import NotificationType
from onyx.db.enums import ApprovalDecision, ScheduledTaskRunStatus
from onyx.db.models import (
    ActionApproval,
    GatedApp,
    ScheduledTask,
    ScheduledTaskGraduation,
    ScheduledTaskPreApprovedTarget,
    ScheduledTaskRun,
)
from onyx.db.notification import create_notification
from onyx.server.features.build.configs import (
    CRAFT_ACTION_AUTO_GRADUATION_ENABLED,
    CRAFT_ACTION_GRADUATION_THRESHOLD,
)
from onyx.utils.logger import setup_logger

logger = setup_logger()


def record_decision_outcome(db_session: Session, *, decided: ActionApproval) -> None:
    """Update graduation progress after a human decision.

    Runs inside the decision endpoint's transaction; the commit stays the
    caller's job. Best-effort by construction: any unexpected shape (target
    cleared, task deleted) simply skips the update.
    """
    target_app = decided.gated_app
    if target_app is None:
        return
    if decided.decision is ApprovalDecision.REJECTED:
        _reset_progress(db_session, task_session_id=decided.session_id, app=target_app)
        return
    if decided.decision is not ApprovalDecision.APPROVED:
        return
    if (
        not CRAFT_ACTION_AUTO_GRADUATION_ENABLED
        or CRAFT_ACTION_GRADUATION_THRESHOLD < 1
    ):
        return
    run = db_session.execute(
        select(ScheduledTaskRun.task_id).where(
            ScheduledTaskRun.session_id == decided.session_id,
            ScheduledTaskRun.status == ScheduledTaskRunStatus.RUNNING,
        )
    ).first()
    if run is None:
        # Interactive session: approvals there are covered by session grants.
        return
    task_id = run[0]
    _bump_progress(
        db_session,
        task_id=task_id,
        app=target_app,
        approval=decided,
    )


def _reset_progress(
    db_session: Session, *, task_session_id: Any, app: GatedApp
) -> None:
    """A rejection wipes the (task, target) counter, wherever it was."""
    db_session.execute(
        delete(ScheduledTaskGraduation).where(
            ScheduledTaskGraduation.gated_app_id == app.id,
            ScheduledTaskGraduation.scheduled_task_id.in_(
                select(ScheduledTaskRun.task_id).where(
                    ScheduledTaskRun.session_id == task_session_id
                )
            ),
        )
    )


def _bump_progress(
    db_session: Session,
    *,
    task_id: Any,
    app: GatedApp,
    approval: ActionApproval,
) -> None:
    counter = db_session.scalar(
        select(ScheduledTaskGraduation).where(
            ScheduledTaskGraduation.scheduled_task_id == task_id,
            ScheduledTaskGraduation.gated_app_id == app.id,
        )
    )
    if counter is None:
        counter = ScheduledTaskGraduation(
            scheduled_task_id=task_id,
            gated_app_id=app.id,
            consecutive_passes=0,
            policy_version=app.policy_version,
        )
        db_session.add(counter)
        db_session.flush()
    if counter.policy_version != app.policy_version:
        # The policy changed since these passes accumulated: start over.
        counter.consecutive_passes = 0
        counter.policy_version = app.policy_version

    counter.consecutive_passes += 1
    logger.info(
        "approval.graduation_progress task_id=%s gated_app_id=%s "
        "passes=%s threshold=%s policy_version=%s",
        task_id,
        app.id,
        counter.consecutive_passes,
        CRAFT_ACTION_GRADUATION_THRESHOLD,
        app.policy_version,
    )
    if counter.consecutive_passes < CRAFT_ACTION_GRADUATION_THRESHOLD:
        return

    # Graduate: the pre-approval row (bound to the current policy version) is
    # the durable "auto" state; the counter's job is done.
    existing = db_session.scalar(
        select(ScheduledTaskPreApprovedTarget).where(
            ScheduledTaskPreApprovedTarget.scheduled_task_id == task_id,
            ScheduledTaskPreApprovedTarget.gated_app_id == app.id,
        )
    )
    if existing is None:
        db_session.add(
            ScheduledTaskPreApprovedTarget(
                scheduled_task_id=task_id,
                gated_app_id=app.id,
                policy_version=app.policy_version,
            )
        )
    db_session.delete(counter)
    _notify_graduation(db_session, task_id=task_id, approval=approval)


def _notify_graduation(
    db_session: Session, *, task_id: Any, approval: ActionApproval
) -> None:
    """Best-effort per-user notification; never masks the graduation itself."""
    try:
        task = db_session.get(ScheduledTask, task_id)
        if task is None:
            return
        create_notification(
            user_id=task.user_id,
            notif_type=NotificationType.SCHEDULED_TASK_PRE_APPROVED_ACTION,
            db_session=db_session,
            title=(
                f'Scheduled task "{task.name}" now auto-approves '
                f"{approval.app_name} actions after supervised runs"
            ),
            additional_data={"task_id": str(task_id)},
            autocommit=False,
        )
    except Exception:
        logger.warning(
            "approval.graduation_notification_failed task_id=%s", task_id, exc_info=True
        )
