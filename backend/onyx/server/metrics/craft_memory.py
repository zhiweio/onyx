"""Prometheus metrics for the Craft long-term memory tools (P5).

Best-effort only: a metrics failure never propagates into a turn.
"""

import logging

from prometheus_client import Counter

logger = logging.getLogger(__name__)

_memory_tool_outcomes_total = Counter(
    "onyx_craft_memory_tool_total",
    "Craft memory tool calls by tool and outcome "
    "(stored/rejected/forbidden/disabled/hit/empty).",
    labelnames=["tool", "outcome"],
)


def record_memory_tool_outcome(tool: str, outcome: str) -> None:
    try:
        _memory_tool_outcomes_total.labels(tool=tool, outcome=outcome).inc()
    except Exception:
        logger.debug("Failed to record memory tool outcome.", exc_info=True)
