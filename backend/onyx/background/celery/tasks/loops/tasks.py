"""Craft loop celery tasks.

- ``loops_fire_sweep`` (primary queue, per tenant, every 30 s): claims
  due ``CraftLoop`` rows, reclaims expired item claim leases, claims
  queued items up to each loop's per-fire cap and dispatches one
  ``loops_fire_item`` per item. Lightweight DB-only work, so primary.
- ``loops_fire_item(item_id, claim_token)`` (``scheduled_tasks`` queue):
  delegation to ``run_loop_item_logic``; shares the dedicated
  long-running worker pool with the scheduled-task executor.

Per CLAUDE.md: ``@shared_task``, ``expires=`` on every enqueue, budgets
enforced inside the executor.
"""

from __future__ import annotations

from celery import Task, shared_task

from onyx.configs.constants import OnyxCeleryPriority, OnyxCeleryQueues, OnyxCeleryTask
from onyx.server.features.build.loops.fire import (
    loops_fire_sweep_logic,
    run_loop_item_logic,
)
from onyx.server.features.build.timeouts import QUEUE_RESIDENCY_SECONDS
from onyx.utils.logger import setup_logger

logger = setup_logger()

ITEM_EXPIRES_SECONDS = QUEUE_RESIDENCY_SECONDS


@shared_task(  # ty: ignore[invalid-argument-type]
    name=OnyxCeleryTask.LOOPS_FIRE_SWEEP,
    ignore_result=True,
    bind=True,
)
def loops_fire_sweep(self: Task, *, tenant_id: str) -> int:
    """Sweep due loops and dispatch per-item executor tasks."""
    manifest = loops_fire_sweep_logic()
    for entry in manifest:
        self.app.send_task(
            OnyxCeleryTask.LOOPS_FIRE_ITEM,
            kwargs={
                "item_id": entry["item_id"],
                "claim_token": entry["claim_token"],
                "tenant_id": tenant_id,
            },
            queue=OnyxCeleryQueues.SCHEDULED_TASKS,
            priority=OnyxCeleryPriority.MEDIUM,
            expires=ITEM_EXPIRES_SECONDS,
            headers={"enqueued_at": __import__("time").time()},
        )
    if manifest:
        logger.info(
            "loops_fire_sweep tenant=%s dispatched=%d", tenant_id, len(manifest)
        )
    return len(manifest)


@shared_task(  # ty: ignore[invalid-argument-type]
    name=OnyxCeleryTask.LOOPS_FIRE_ITEM,
    ignore_result=True,
    bind=True,
)
def loops_fire_item(
    self: Task, *, item_id: str, claim_token: str, tenant_id: str
) -> None:
    del self, tenant_id
    from uuid import UUID

    run_loop_item_logic(UUID(item_id), claim_token=claim_token)
