from datetime import datetime, timezone

from celery import shared_task
from croniter import croniter

from onyx.configs.constants import OnyxCeleryQueues, OnyxCeleryTask
from onyx.db.engine.sql_engine import get_session_with_current_tenant
from onyx.db.enums import MCPGatewayRefreshMode
from onyx.db.mcp_gateway import (
    list_entries_for_scheduled_refresh,
    list_policies_for_provider,
    list_providers,
)
from onyx.mcp_gateway.engine import refresh_entry
from onyx.utils.logger import setup_logger
from shared_configs.contextvars import get_current_tenant_id

logger = setup_logger()


@shared_task(  # ty: ignore[invalid-argument-type]
    name=OnyxCeleryTask.REFRESH_MCP_GATEWAY_CACHE_ENTRY,
    ignore_result=True,
    trail=False,
    queue=OnyxCeleryQueues.MCP_GATEWAY,
)
def refresh_mcp_gateway_cache_entry(
    *,
    tenant_id: str,  # noqa: ARG001
    cache_key: str,
) -> None:
    import asyncio

    asyncio.run(refresh_entry(get_current_tenant_id(), cache_key))


@shared_task(  # ty: ignore[invalid-argument-type]
    name=OnyxCeleryTask.CHECK_MCP_GATEWAY_SCHEDULED_REFRESH,
    ignore_result=True,
    trail=False,
    queue=OnyxCeleryQueues.MCP_GATEWAY,
)
def check_mcp_gateway_scheduled_refresh(*, tenant_id: str) -> None:
    now = datetime.now(timezone.utc)
    with get_session_with_current_tenant() as db_session:
        for provider in list_providers(db_session, enabled_only=True):
            policies = list_policies_for_provider(db_session, provider.slug)
            names: list[str] = []
            for policy in policies:
                if policy.refresh_mode not in (
                    MCPGatewayRefreshMode.SCHEDULE,
                    MCPGatewayRefreshMode.TTL_AND_SCHEDULE,
                ):
                    continue
                if not policy.schedule_cron:
                    continue
                if not croniter.is_valid(policy.schedule_cron):
                    continue
                names.append(policy.tool_name)
            if not names:
                continue
            entries = list_entries_for_scheduled_refresh(
                db_session,
                tenant_id=tenant_id,
                provider_slug=provider.slug,
                tool_names=names,
                older_than=now,
                limit=100,
            )
            for entry in entries:
                refresh_mcp_gateway_cache_entry.apply_async(
                    kwargs={"tenant_id": tenant_id, "cache_key": entry.cache_key},
                    expires=600,
                )
