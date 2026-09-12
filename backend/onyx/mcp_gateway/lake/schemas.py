"""Iceberg table schemas for the MCP gateway lake."""

from pyiceberg.partitioning import PartitionField, PartitionSpec
from pyiceberg.schema import Schema
from pyiceberg.transforms import DayTransform, IdentityTransform
from pyiceberg.types import (
    BooleanType,
    LongType,
    NestedField,
    StringType,
    TimestamptzType,
)

SCHEMA_VERSION = 1

FACT_RESULTS = Schema(
    NestedField(1, "tenant_id", StringType(), required=True),
    NestedField(2, "blob_id", StringType(), required=True),
    NestedField(3, "catalog_slug", StringType(), required=True),
    NestedField(4, "blob_prefix", StringType(), required=True),
    NestedField(5, "effective_tool_name", StringType(), required=True),
    NestedField(6, "payload", StringType(), required=True),
    NestedField(7, "digest", StringType(), required=True),
    NestedField(8, "size_bytes", LongType(), required=True),
    NestedField(9, "is_empty", BooleanType(), required=True),
    NestedField(10, "is_error", BooleanType(), required=True),
    NestedField(11, "schema_version", LongType(), required=True),
    NestedField(12, "created_at", TimestamptzType(), required=True),
    NestedField(13, "recorded_at", TimestamptzType(), required=True),
)
FACT_RESULTS_SPEC = PartitionSpec(
    PartitionField(1, 1000, IdentityTransform(), "tenant_id"),
    PartitionField(3, 1001, IdentityTransform(), "catalog_slug"),
    PartitionField(12, 1002, DayTransform(), "created_at_day"),
    PartitionField(4, 1003, IdentityTransform(), "blob_prefix"),
)

FACT_CALLS = Schema(
    NestedField(1, "tenant_id", StringType(), required=True),
    NestedField(2, "call_id", StringType(), required=True),
    NestedField(3, "parent_call_id", StringType(), required=False),
    NestedField(4, "request_id", StringType(), required=True),
    NestedField(5, "catalog_slug", StringType(), required=True),
    NestedField(6, "pack_slug", StringType(), required=True),
    NestedField(7, "tool_name", StringType(), required=True),
    NestedField(8, "effective_tool_name", StringType(), required=True),
    NestedField(9, "cache_key", StringType(), required=True),
    NestedField(10, "result_blob_id", StringType(), required=False),
    NestedField(11, "outcome", StringType(), required=True),
    NestedField(12, "is_error", BooleanType(), required=True),
    NestedField(13, "error_class", StringType(), required=False),
    NestedField(14, "error_message", StringType(), required=False),
    NestedField(15, "upstream_billed", BooleanType(), required=True),
    NestedField(16, "latency_ms", LongType(), required=True),
    NestedField(17, "response_bytes", LongType(), required=True),
    NestedField(18, "user_id", StringType(), required=False),
    NestedField(19, "user_email", StringType(), required=False),
    NestedField(20, "session_id", StringType(), required=False),
    NestedField(21, "arguments", StringType(), required=True),
    NestedField(22, "arguments_digest", StringType(), required=True),
    NestedField(23, "refresh_mode", StringType(), required=True),
    NestedField(24, "ttl_seconds", LongType(), required=True),
    NestedField(25, "schema_version", LongType(), required=True),
    NestedField(26, "created_at", TimestamptzType(), required=True),
    NestedField(27, "recorded_at", TimestamptzType(), required=True),
)
FACT_CALLS_SPEC = PartitionSpec(
    PartitionField(1, 1100, IdentityTransform(), "tenant_id"),
    PartitionField(26, 1101, DayTransform(), "created_at_day"),
    PartitionField(5, 1102, IdentityTransform(), "catalog_slug"),
)

FACT_CACHE_EVENTS = Schema(
    NestedField(1, "tenant_id", StringType(), required=True),
    NestedField(2, "event_id", StringType(), required=True),
    NestedField(3, "cache_key", StringType(), required=True),
    NestedField(4, "blob_id", StringType(), required=False),
    NestedField(5, "call_id", StringType(), required=False),
    NestedField(6, "action", StringType(), required=True),
    NestedField(7, "catalog_slug", StringType(), required=True),
    NestedField(8, "schema_version", LongType(), required=True),
    NestedField(9, "created_at", TimestamptzType(), required=True),
    NestedField(10, "recorded_at", TimestamptzType(), required=True),
)
FACT_CACHE_EVENTS_SPEC = PartitionSpec(
    PartitionField(1, 1200, IdentityTransform(), "tenant_id"),
    PartitionField(9, 1201, DayTransform(), "created_at_day"),
)

DIM_CATALOG = Schema(
    NestedField(1, "tenant_id", StringType(), required=True),
    NestedField(2, "catalog_sk", StringType(), required=True),
    NestedField(3, "catalog_slug", StringType(), required=True),
    NestedField(4, "pack_slug", StringType(), required=True),
    NestedField(5, "display_name", StringType(), required=True),
    NestedField(6, "upstream_host", StringType(), required=True),
    NestedField(7, "enabled", BooleanType(), required=True),
    NestedField(8, "is_current", BooleanType(), required=True),
    NestedField(9, "valid_from", TimestamptzType(), required=True),
    NestedField(10, "valid_to", TimestamptzType(), required=False),
    NestedField(11, "schema_version", LongType(), required=True),
    NestedField(12, "recorded_at", TimestamptzType(), required=True),
)
DIM_CATALOG_SPEC = PartitionSpec(
    PartitionField(1, 1300, IdentityTransform(), "tenant_id"),
)

DIM_TOOL = Schema(
    NestedField(1, "tenant_id", StringType(), required=True),
    NestedField(2, "tool_sk", StringType(), required=True),
    NestedField(3, "catalog_slug", StringType(), required=True),
    NestedField(4, "tool_name", StringType(), required=True),
    NestedField(5, "enabled", BooleanType(), required=True),
    NestedField(6, "is_current", BooleanType(), required=True),
    NestedField(7, "valid_from", TimestamptzType(), required=True),
    NestedField(8, "valid_to", TimestamptzType(), required=False),
    NestedField(9, "schema_version", LongType(), required=True),
    NestedField(10, "recorded_at", TimestamptzType(), required=True),
)
DIM_TOOL_SPEC = PartitionSpec(
    PartitionField(1, 1400, IdentityTransform(), "tenant_id"),
    PartitionField(3, 1401, IdentityTransform(), "catalog_slug"),
)

AGG_STATS_DAILY = Schema(
    NestedField(1, "tenant_id", StringType(), required=True),
    NestedField(2, "catalog_slug", StringType(), required=True),
    NestedField(3, "day", StringType(), required=True),
    NestedField(4, "outcome", StringType(), required=True),
    NestedField(5, "call_count", LongType(), required=True),
    NestedField(6, "billed_count", LongType(), required=True),
    NestedField(7, "response_bytes", LongType(), required=True),
    NestedField(8, "latency_ms_sum", LongType(), required=True),
    NestedField(9, "schema_version", LongType(), required=True),
    NestedField(10, "recorded_at", TimestamptzType(), required=True),
)
AGG_STATS_DAILY_SPEC = PartitionSpec(
    PartitionField(1, 1500, IdentityTransform(), "tenant_id"),
    PartitionField(
        source_id=3,
        field_id=1501,
        transform=IdentityTransform(),
        name="day",
    ),
)

# day is a string YYYY-MM-DD; month rollup is done in SQL / pyarrow.
# Keep an identity partition on day so expire can drop old days.
# MonthTransform needs a date/timestamp source; we use identity(day) instead.

TABLES: tuple[tuple[str, Schema, PartitionSpec], ...] = (
    ("fact_results", FACT_RESULTS, FACT_RESULTS_SPEC),
    ("fact_calls", FACT_CALLS, FACT_CALLS_SPEC),
    ("fact_cache_events", FACT_CACHE_EVENTS, FACT_CACHE_EVENTS_SPEC),
    ("dim_catalog", DIM_CATALOG, DIM_CATALOG_SPEC),
    ("dim_tool", DIM_TOOL, DIM_TOOL_SPEC),
    ("agg_stats_daily", AGG_STATS_DAILY, AGG_STATS_DAILY_SPEC),
)
