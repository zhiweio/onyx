"""Celery tasks for the craft golden-set eval pipeline.

Thin wrappers around the logic in
``onyx.server.features.build.evals.pipeline`` so external-dependency unit
tests can drive the pipeline directly (same split as scheduled tasks).
"""

from celery import Task, shared_task

from onyx.background.celery.apps.app_base import task_logger
from onyx.configs.constants import OnyxCeleryQueues, OnyxCeleryTask
from onyx.db.engine.sql_engine import get_session_with_current_tenant

# A full run is ~6 cases × up to 45 min + judging; the soft limit only
# guards a wedged worker (each case enforces its own budget too).
RUN_SOFT_TIME_LIMIT = 6 * 3600


@shared_task(  # ty: ignore[invalid-argument-type]
    name=OnyxCeleryTask.CRAFT_EVAL_RUN,
    soft_time_limit=RUN_SOFT_TIME_LIMIT,
    bind=True,
    ignore_result=True,
)
def craft_eval_run_task(
    self: Task,  # noqa: ARG001
    *,
    run_id: str,
    tenant_id: str,  # noqa: ARG001
) -> None:
    """Execute one already-created eval run to a terminal status."""
    from onyx.server.features.build.evals.pipeline import run_eval_pipeline

    run_eval_pipeline(run_id)  # type: ignore[arg-type]


@shared_task(  # ty: ignore[invalid-argument-type]
    name=OnyxCeleryTask.CRAFT_EVAL_NIGHTLY,
    soft_time_limit=600,
    bind=True,
    ignore_result=True,
)
def craft_eval_nightly_task(
    self: Task,  # noqa: ARG001
    *,
    tenant_id: str,
) -> None:
    """Nightly regression beat: prune old runs, create a nightly run over
    the full case set, and hand it to the run executor."""
    from celery import current_app

    from onyx.db.craft_evals import (
        eval_run_retention_cutoff,
        prune_eval_runs_before,
    )
    from onyx.db.enums import CraftEvalRunTrigger
    from onyx.server.features.build.configs import CRAFT_EVAL_RETENTION_DAYS
    from onyx.server.features.build.evals.pipeline import create_eval_run_for_cases

    with get_session_with_current_tenant() as db_session:
        removed = prune_eval_runs_before(
            db_session,
            eval_run_retention_cutoff(CRAFT_EVAL_RETENTION_DAYS),
        )
        run, _cases = create_eval_run_for_cases(
            db_session, trigger=CraftEvalRunTrigger.NIGHTLY
        )
        db_session.commit()
    if removed:
        task_logger.info(
            "craft_eval_nightly pruned=%s runs tenant=%s", removed, tenant_id
        )
    task_logger.info(
        "craft_eval_nightly dispatched run=%s tenant=%s", run.id, tenant_id
    )
    current_app.send_task(
        OnyxCeleryTask.CRAFT_EVAL_RUN,
        kwargs={"run_id": str(run.id), "tenant_id": tenant_id},
        queue=OnyxCeleryQueues.SCHEDULED_TASKS,
    )
