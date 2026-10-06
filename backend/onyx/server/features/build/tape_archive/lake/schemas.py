"""Iceberg table schemas for the craft tape archive lake.

Mirrors the MCP gateway lake conventions: every table carries
``schema_version`` and ``recorded_at``, is identity-partitioned by tenant,
and day-partitioned by its primary timestamp so retention can drop whole
days. Field ids start at 2100 to stay distinct from the MCP lake tables
that share the catalog schema.
"""

from pyiceberg.partitioning import PartitionField, PartitionSpec
from pyiceberg.schema import Schema
from pyiceberg.transforms import DayTransform, IdentityTransform
from pyiceberg.types import (
    DoubleType,
    LongType,
    NestedField,
    StringType,
    TimestamptzType,
)

SCHEMA_VERSION = 1

FACT_TAPE_EVENTS = Schema(
    NestedField(1, "tenant_id", StringType(), required=True),
    NestedField(2, "session_id", StringType(), required=True),
    NestedField(3, "turn_index", LongType(), required=False),
    NestedField(4, "source_id", LongType(), required=True),
    NestedField(5, "kind", StringType(), required=True),
    NestedField(6, "subtype", StringType(), required=True),
    NestedField(7, "runtime", StringType(), required=True),
    # Recording surface, reserved for future non-craft agent tapes.
    NestedField(8, "source", StringType(), required=True),
    NestedField(9, "payload", StringType(), required=True),
    NestedField(10, "batch_id", StringType(), required=True),
    NestedField(11, "schema_version", LongType(), required=True),
    NestedField(12, "created_at", TimestamptzType(), required=True),
    NestedField(13, "recorded_at", TimestamptzType(), required=True),
)
FACT_TAPE_EVENTS_SPEC = PartitionSpec(
    PartitionField(1, 2100, IdentityTransform(), "tenant_id"),
    PartitionField(12, 2101, DayTransform(), "created_at_day"),
)

FACT_TURNS = Schema(
    NestedField(1, "tenant_id", StringType(), required=True),
    NestedField(2, "session_id", StringType(), required=True),
    NestedField(3, "turn_index", LongType(), required=True),
    NestedField(4, "runtime", StringType(), required=True),
    NestedField(5, "user_id", StringType(), required=False),
    NestedField(6, "origin", StringType(), required=False),
    NestedField(7, "started_at", TimestamptzType(), required=False),
    NestedField(8, "ended_at", TimestamptzType(), required=False),
    NestedField(9, "event_count", LongType(), required=True),
    NestedField(10, "input_tokens", LongType(), required=False),
    NestedField(11, "output_tokens", LongType(), required=False),
    NestedField(12, "reasoning_tokens", LongType(), required=False),
    NestedField(13, "cache_read_tokens", LongType(), required=False),
    NestedField(14, "cache_write_tokens", LongType(), required=False),
    NestedField(15, "cost", DoubleType(), required=False),
    # turn/end reason from the tape's lifecycle context event; an open
    # turn (no end event recorded) archives as "interrupted".
    NestedField(16, "turn_end_reason", StringType(), required=False),
    NestedField(17, "error_detail", StringType(), required=False),
    NestedField(18, "model", StringType(), required=False),
    NestedField(19, "batch_id", StringType(), required=True),
    NestedField(20, "schema_version", LongType(), required=True),
    NestedField(21, "recorded_at", TimestamptzType(), required=True),
)
FACT_TURNS_SPEC = PartitionSpec(
    PartitionField(1, 2200, IdentityTransform(), "tenant_id"),
    PartitionField(7, 2201, DayTransform(), "started_at_day"),
)

TABLES: tuple[tuple[str, Schema, PartitionSpec], ...] = (
    ("fact_tape_events", FACT_TAPE_EVENTS, FACT_TAPE_EVENTS_SPEC),
    ("fact_turns", FACT_TURNS, FACT_TURNS_SPEC),
)
