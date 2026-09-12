import asyncio
from datetime import datetime, timedelta, timezone

from celery import shared_task
from croniter import croniter

from onyx.configs.app_configs import (
    MCP_GATEWAY_CALL_LOG_RETENTION_DAYS,
    MCP_RESULT_BLOB_TTL_DAYS,
)
from onyx.configs.constants import OnyxCeleryQueues, OnyxCeleryTask
from onyx.db.engine.sql_engine import get_session_with_current_tenant
from onyx.db.enums import MCPGatewayRefreshMode, MCPResultStorage
from onyx.db.mcp_catalog import list_catalog_entries
from onyx.db.mcp_gateway import (
    delete_blobs,
    list_entries_for_scheduled_refresh,
    list_expired_blobs,
)
from onyx.db.mcp_iceberg import delete_results, expire_calls_before, lake_rollup_day
from onyx.mcp_gateway.engine import refresh_entry
from onyx.mcp_gateway.policy import effective_policies
from onyx.mcp_gateway.service import is_gateway_enabled
from onyx.mcp_gateway.storage import delete_object
from onyx.utils.logger import setup_logger
from shared_configs.contextvars import get_current_tenant_id

logger = setup_logger()

# One pass deletes at most this many blobs, so a large backlog is worked
# through over several runs instead of in one long transaction.
_CLEANUP_BATCH_SIZE = 500


@shared_task(
    name=OnyxCeleryTask.REFRESH_MCP_GATEWAY_CACHE_ENTRY,
    ignore_result=True,
    trail=False,
    queue=OnyxCeleryQueues.MCP_GATEWAY,
)
def refresh_mcp_gateway_cache_entry(
    *,
    tenant_id: str,  # noqa: ARG001 — TenantAwareTask already bound the context
    cache_key: str,
) -> None:
    if not is_gateway_enabled():
        return
    asyncio.run(refresh_entry(get_current_tenant_id(), cache_key))


@shared_task(
    name=OnyxCeleryTask.CHECK_MCP_GATEWAY_SCHEDULED_REFRESH,
    ignore_result=True,
    trail=False,
    queue=OnyxCeleryQueues.MCP_GATEWAY,
)
def check_mcp_gateway_scheduled_refresh(*, tenant_id: str) -> None:
    """Re-fetch entries whose policy says they are due on a schedule."""
    if not is_gateway_enabled():
        return

    now = datetime.now(timezone.utc)
    with get_session_with_current_tenant() as db_session:
        for entry in list_catalog_entries(db_session, enabled_only=True):
            scheduled_labels = [
                label
                for label, spec, _ in effective_policies(
                    entry.pack_slug, entry.policy_overrides
                )
                if spec.refresh_mode
                in (
                    MCPGatewayRefreshMode.SCHEDULE,
                    MCPGatewayRefreshMode.TTL_AND_SCHEDULE,
                )
                and spec.schedule_cron
                and croniter.is_valid(spec.schedule_cron)
            ]
            if not scheduled_labels:
                continue

            due = list_entries_for_scheduled_refresh(
                db_session,
                catalog_slug=entry.slug,
                tool_names=scheduled_labels,
                older_than=now,
                limit=100,
            )
            for cache_entry in due:
                refresh_mcp_gateway_cache_entry.apply_async(
                    kwargs={
                        "tenant_id": tenant_id,
                        "cache_key": cache_entry.cache_key,
                    },
                    expires=600,
                )


@shared_task(
    name=OnyxCeleryTask.CLEANUP_MCP_RESULT_BLOBS,
    ignore_result=True,
    trail=False,
    queue=OnyxCeleryQueues.MCP_GATEWAY,
)
def cleanup_mcp_result_blobs(*, tenant_id: str) -> None:  # noqa: ARG001
    """Delete result bodies nobody has read for a while.

    Deletion is driven by `last_accessed_at`, not creation time, so a body a
    long-running conversation keeps reading stays put. Cache entries reference
    blobs with ON DELETE CASCADE, so a collected body takes its cache entry
    with it and the next call refetches.

    The object store is cleared first: an orphaned row is recoverable on the
    next pass, an orphaned object is not.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=MCP_RESULT_BLOB_TTL_DAYS)

    with get_session_with_current_tenant() as db_session:
        expired = list_expired_blobs(
            db_session, older_than=cutoff, limit=_CLEANUP_BATCH_SIZE
        )
        if not expired:
            return
        targets = [
            (blob.id, blob.file_id if blob.storage == MCPResultStorage.OBJECT else None)
            for blob in expired
        ]

    blob_ids = [blob_id for blob_id, _ in targets]
    delete_results(blob_ids)
    for _blob_id, file_id in targets:
        if file_id:
            delete_object(file_id)

    with get_session_with_current_tenant() as db_session:
        deleted = delete_blobs(db_session, blob_ids)

    logger.info("Deleted %s expired MCP result blobs", deleted)


@shared_task(
    name=OnyxCeleryTask.ROLLUP_MCP_GATEWAY_CALL_STATS,
    ignore_result=True,
    trail=False,
    queue=OnyxCeleryQueues.MCP_GATEWAY,
)
def rollup_mcp_gateway_call_stats(*, tenant_id: str) -> None:  # noqa: ARG001
    yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)
    written = lake_rollup_day(yesterday)
    logger.info("Rolled up MCP gateway call stats for %s (%s rows)", yesterday, written)


@shared_task(
    name=OnyxCeleryTask.PRUNE_MCP_GATEWAY_CALL_LOGS,
    ignore_result=True,
    trail=False,
    queue=OnyxCeleryQueues.MCP_GATEWAY,
)
def prune_mcp_gateway_call_logs(*, tenant_id: str) -> None:  # noqa: ARG001
    if MCP_GATEWAY_CALL_LOG_RETENTION_DAYS <= 0:
        logger.info("MCP gateway call log retention is unlimited; skip prune")
        return
    cutoff = datetime.now(timezone.utc) - timedelta(
        days=MCP_GATEWAY_CALL_LOG_RETENTION_DAYS
    )
    deleted = expire_calls_before(cutoff)
    logger.info(
        "Expired %s MCP gateway Iceberg call rows older than %s", deleted, cutoff
    )
