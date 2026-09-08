"""Delta checkpoints and replay for a Craft job."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from onyx.server.features.build.jobs.channels import JobState, apply_writes, empty_state


def save_delta(
    db_session: Session,
    *,
    job_id: UUID,
    ns: str,
    step: int,
    writes: dict[str, Any],
) -> None:
    from onyx.db.craft_job import add_job_checkpoint

    add_job_checkpoint(db_session, job_id=job_id, ns=ns, step=step, writes=writes)


def replay_deltas(
    db_session: Session, *, job_id: UUID, ns: str | None = None
) -> JobState:
    from onyx.db.craft_job import list_job_checkpoints

    state = empty_state()
    for row in list_job_checkpoints(db_session, job_id=job_id, ns=ns):
        writes = row.writes if isinstance(row.writes, dict) else {}
        state = apply_writes(state, writes)
    return state
