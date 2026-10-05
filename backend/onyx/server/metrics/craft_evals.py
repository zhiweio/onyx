"""Prometheus metrics for the Craft golden-set eval pipeline (P4).

Per-case outcomes and whole-run durations. Best-effort only: a metrics
failure never propagates into the eval pipeline.
"""

import logging

from prometheus_client import Counter, Histogram

logger = logging.getLogger(__name__)

_eval_case_outcomes_total = Counter(
    "onyx_craft_eval_case_total",
    "Craft eval case results by outcome (pass/fail/error).",
    labelnames=["outcome"],
)

_eval_run_duration_seconds = Histogram(
    "onyx_craft_eval_run_duration_seconds",
    "Craft eval pipeline wall-clock duration for a whole run.",
    buckets=[60, 600, 1800, 3600, 7200, 14400, 28800],
)


def record_case_outcome(outcome: str) -> None:
    try:
        _eval_case_outcomes_total.labels(outcome=outcome).inc()
    except Exception:
        logger.debug("Failed to record eval case outcome.", exc_info=True)


def record_run_duration(duration_seconds: float) -> None:
    try:
        _eval_run_duration_seconds.observe(duration_seconds)
    except Exception:
        logger.debug("Failed to record eval run duration.", exc_info=True)
