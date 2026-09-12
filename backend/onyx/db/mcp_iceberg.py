"""Repository for MCP Iceberg facts. Callers stay in onyx.db."""

from datetime import date, datetime
from typing import Any

from onyx.mcp_gateway.lake.catalog import ensure_mcp_iceberg_tables
from onyx.mcp_gateway.lake.io import (
    CallRecord,
    ResultRecord,
    append_cache_event,
    append_call,
    append_result,
    blob_prefix_for,
    clear_tenant_lake,
    delete_catalog_calls,
    delete_results,
    expire_calls_before,
    get_call,
    get_result,
    list_calls,
    result_exists,
    rollup_daily_stats,
    snapshot_catalog,
    snapshot_tool,
    stats_series,
    stats_windowed,
)

__all__ = [
    "CallRecord",
    "ResultRecord",
    "append_cache_event",
    "append_call",
    "append_result",
    "blob_prefix_for",
    "clear_tenant_lake",
    "delete_catalog_calls",
    "delete_results",
    "ensure_mcp_iceberg_tables",
    "expire_calls_before",
    "get_call",
    "get_result",
    "list_calls",
    "result_exists",
    "rollup_daily_stats",
    "snapshot_catalog",
    "snapshot_tool",
    "stats_series",
    "stats_windowed",
]


def lake_stats(
    *,
    from_time: datetime,
    to_time: datetime,
    catalog_slug: str | None = None,
) -> dict[str, Any]:
    return stats_windowed(
        from_time=from_time, to_time=to_time, catalog_slug=catalog_slug
    )


def lake_series(
    *,
    from_time: datetime,
    to_time: datetime,
    catalog_slug: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    return stats_series(from_time=from_time, to_time=to_time, catalog_slug=catalog_slug)


def lake_rollup_day(day: date) -> int:
    return rollup_daily_stats(day=day)
