"""Run journal for Craft jobs. UI and debug read these events."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

RUN_START = "run.start"
NODE_START = "node.start"
NODE_END = "node.end"
GATE_FAIL = "gate.fail"
LANE_START = "lane.start"
LANE_END = "lane.end"
INTERRUPT = "interrupt"
RESUME = "resume"
DRAIN = "run.drain"
DELIVERY = "run.delivery"


def emit(
    db_session: Session,
    *,
    job_id: UUID,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> None:
    from onyx.db.craft_job import append_job_event

    append_job_event(
        db_session,
        job_id=job_id,
        event_type=event_type,
        payload=payload or {},
    )
