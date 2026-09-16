"""Celery tasks for sandbox operations (cleanup, etc.)."""

import datetime
import time

from celery import Task, shared_task
from redis.lock import Lock as RedisLock
from sqlalchemy.orm import Session as DBSession

from onyx.background.celery.apps.app_base import task_logger
from onyx.configs.constants import OnyxCeleryTask, OnyxRedisLocks
from onyx.db.engine.sql_engine import get_session_with_current_tenant
from onyx.db.models import Sandbox
from onyx.redis.redis_pool import get_redis_client
from onyx.redis.redis_tenant_work_gating import maybe_mark_tenant_active
from onyx.redis.tenant_redis_client import TenantRedisClient
from onyx.server.features.build.configs import (
    SANDBOX_HIBERNATE_MAX_AGE_SECONDS,
    SANDBOX_SNAPSHOT_INTERVAL_SECONDS,
)
from onyx.server.features.build.db.sandbox import (
    count_hibernated_sandboxes,
    get_hibernated_sandboxes_older_than,
    get_latest_snapshot_for_session,
    get_running_sandboxes,
    user_has_stale_active_session,
)
from onyx.server.features.build.sandbox.base import SandboxManager
from onyx.server.features.build.sandbox.factory import get_sandbox_manager
from onyx.server.features.build.session.locks import get_session_creation_lock
from onyx.server.features.build.session.sandbox_lifecycle import (
    archive_sandbox,
    create_session_snapshot_keep_latest,
    hibernate_sandbox,
    list_snapshotable_session_workspaces,
    should_sleep_sandbox,
    sleep_sandbox,
)
from onyx.server.metrics.craft_sandbox import set_hibernated_sandbox_count

# 100 minutes - snapshotting can take time
TIMEOUT_SECONDS = 6000


@shared_task(  # ty: ignore[invalid-argument-type]
    name=OnyxCeleryTask.CLEANUP_IDLE_SANDBOXES,
    soft_time_limit=TIMEOUT_SECONDS,
    bind=True,
    ignore_result=True,
)
def cleanup_idle_sandboxes_task(self: Task, *, tenant_id: str) -> None:  # noqa: ARG001
    """Sweep sandboxes along their lifecycle: background-snapshot active
    ones, hibernate or sleep idle ones, archive stale hibernated ones.

    Idle lane, by backend capability: hibernation-capable backends (Docker)
    stop the runtime and keep it for a fast wake; others (Kubernetes)
    snapshot and destroy it (``sleep_sandbox``).

    Background snapshots bound data loss from ungraceful runtime death
    (kubelet eviction, node loss, spot reclaim) to
    ``SANDBOX_SNAPSHOT_INTERVAL_SECONDS``: sessions whose latest snapshot is
    fresher than that interval are skipped without touching the runtime
    (except at reap — the runtime is about to die, so always snapshot). The
    reap itself stays fail-closed: snapshot failure on a reachable runtime
    keeps the sandbox RUNNING for retry next sweep. The hibernate lane is
    fail-open — the stopped runtime keeps its data, so a failed history
    snapshot never blocks the stop.

    The archive sweep reclaims disk: a sandbox hibernated longer than
    ``SANDBOX_HIBERNATE_MAX_AGE_SECONDS`` is snapshotted (fail-closed) and
    its retained runtime destroyed.
    """
    task_logger.info(f"cleanup_idle_sandboxes_task starting for tenant {tenant_id}")

    redis_client = get_redis_client(tenant_id=tenant_id)
    lock: RedisLock = redis_client.lock(
        OnyxRedisLocks.CLEANUP_IDLE_SANDBOXES_BEAT_LOCK,
        timeout=TIMEOUT_SECONDS,
    )

    # Prevent overlapping runs of this task
    if not lock.acquire(blocking=False):
        task_logger.info("cleanup_idle_sandboxes_task - lock not acquired, skipping")
        return

    try:
        sandbox_manager = get_sandbox_manager()

        with get_session_with_current_tenant() as db_session:
            running_sandboxes = get_running_sandboxes(db_session)
            if not running_sandboxes:
                task_logger.debug("No running sandboxes found")
            else:
                _sweep_running_sandboxes(
                    db_session,
                    sandbox_manager,
                    running_sandboxes,
                    tenant_id,
                    redis_client,
                )

            _archive_stale_hibernated_sandboxes(
                db_session, sandbox_manager, tenant_id, redis_client
            )
            set_hibernated_sandbox_count(count_hibernated_sandboxes(db_session))

    except Exception:
        task_logger.exception("Error in cleanup_idle_sandboxes_task")
        raise

    finally:
        if lock.owned():
            lock.release()

    task_logger.info("cleanup_idle_sandboxes_task completed")


def _sweep_running_sandboxes(
    db_session: DBSession,
    sandbox_manager: SandboxManager,
    running_sandboxes: list[Sandbox],
    tenant_id: str,
    redis_client: TenantRedisClient,
) -> None:
    """Background-snapshot active sandboxes; hibernate/sleep idle ones."""
    maybe_mark_tenant_active(tenant_id, caller="sandbox_cleanup")

    now = datetime.datetime.now(datetime.timezone.utc)
    snapshot_cutoff = now - datetime.timedelta(
        seconds=SANDBOX_SNAPSHOT_INTERVAL_SECONDS
    )

    # Partition so idle sandboxes are reaped first (reclaiming runtimes is
    # time-sensitive) before the rest are background-snapshotted.
    idle_sandboxes: list[Sandbox] = []
    non_idle_sandboxes: list[Sandbox] = []
    for sandbox in running_sandboxes:
        (
            idle_sandboxes
            if should_sleep_sandbox(db_session, sandbox, now)
            else non_idle_sandboxes
        ).append(sandbox)

    for sandbox in idle_sandboxes:
        session_creation_lock = get_session_creation_lock(redis_client, sandbox.user_id)
        try:
            if sandbox_manager.supports_hibernation:
                hibernate_sandbox(
                    db_session=db_session,
                    sandbox_manager=sandbox_manager,
                    sandbox=sandbox,
                    tenant_id=tenant_id,
                    session_creation_lock=session_creation_lock,
                )
            else:
                sleep_sandbox(
                    db_session=db_session,
                    sandbox_manager=sandbox_manager,
                    sandbox=sandbox,
                    tenant_id=tenant_id,
                    session_creation_lock=session_creation_lock,
                )
        except Exception as e:
            task_logger.error(
                f"Failed to sweep sandbox {sandbox.id}: {e}",
                exc_info=True,
            )
            db_session.rollback()

    for sandbox in non_idle_sandboxes:
        sandbox_id = sandbox.id

        try:
            # DB-only prefilter: listing workspaces is a runtime exec, so
            # skip it when every ACTIVE session already has a fresh
            # snapshot.
            if not user_has_stale_active_session(
                db_session, sandbox.user_id, snapshot_cutoff
            ):
                continue

            session_creation_lock = get_session_creation_lock(
                redis_client, sandbox.user_id
            )
            if not session_creation_lock.acquire(blocking=False):
                task_logger.info(
                    "Skipping sandbox %s background snapshot while a "
                    "session is being created",
                    sandbox.id,
                )
                continue
            try:
                # List session directories in the sandbox via the
                # backend-agnostic manager API.
                session_ids = list_snapshotable_session_workspaces(
                    db_session,
                    sandbox_manager,
                    sandbox,
                    session_creation_lock,
                )
            finally:
                if session_creation_lock.owned():
                    session_creation_lock.release()

            # Background snapshot failures are log-only (unlike the
            # reap path, nothing is about to be terminated).
            snapshots_created = 0
            for session_id in session_ids:
                try:
                    latest = get_latest_snapshot_for_session(db_session, session_id)
                    if latest and latest.created_at > snapshot_cutoff:
                        continue

                    snapshot_start = time.monotonic()
                    snapshot_result = create_session_snapshot_keep_latest(
                        sandbox_manager=sandbox_manager,
                        db_session=db_session,
                        sandbox_id=sandbox_id,
                        session_id=session_id,
                        tenant_id=tenant_id,
                    )
                    snapshot_elapsed = time.monotonic() - snapshot_start
                    if snapshot_result:
                        snapshots_created += 1
                        task_logger.info(
                            f"Snapshot created for session {session_id}: "
                            f"{snapshot_result.size_bytes / 1_048_576:.1f} MiB "
                            f"in {snapshot_elapsed:.1f}s"
                        )
                except Exception as e:
                    task_logger.warning(
                        f"Failed to create snapshot for session {session_id}: {e}"
                    )
                    db_session.rollback()

            # Chat history lives outside session workspaces;
            # keep it equally fresh.
            if (
                snapshots_created
                and sandbox_manager.supports_opencode_history_persistence
            ):
                try:
                    sandbox_manager.create_opencode_history_snapshot(
                        sandbox_id, tenant_id
                    )
                except Exception as e:
                    task_logger.warning(
                        f"Background opencode history snapshot failed "
                        f"for sandbox {sandbox_id}: {e}"
                    )

        except Exception as e:
            task_logger.error(
                f"Failed to sweep sandbox {sandbox_id}: {e}",
                exc_info=True,
            )
            db_session.rollback()


def _archive_stale_hibernated_sandboxes(
    db_session: DBSession,
    sandbox_manager: SandboxManager,
    tenant_id: str,
    redis_client: TenantRedisClient,
) -> None:
    """Archive hibernated sandboxes asleep past the max age: snapshot them
    and destroy the retained runtime, reclaiming its disk."""
    if not sandbox_manager.supports_hibernation:
        return

    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        seconds=SANDBOX_HIBERNATE_MAX_AGE_SECONDS
    )
    stale = get_hibernated_sandboxes_older_than(db_session, cutoff)
    for sandbox in stale:
        session_creation_lock = get_session_creation_lock(redis_client, sandbox.user_id)
        try:
            archive_sandbox(
                db_session=db_session,
                sandbox_manager=sandbox_manager,
                sandbox=sandbox,
                tenant_id=tenant_id,
                session_creation_lock=session_creation_lock,
            )
        except Exception as e:
            task_logger.error(
                f"Failed to archive hibernated sandbox {sandbox.id}: {e}",
                exc_info=True,
            )
            db_session.rollback()
