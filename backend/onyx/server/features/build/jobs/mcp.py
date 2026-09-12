"""MCP allowlist for Craft long-job turns.

Interactive turns treat an empty picker as "no MCP". Job-owned turns cannot
do that: the host enqueue path never sent the picker, so reconcile would
wipe servers the brief already named. Persist the start-of-job picker on
``JobState``. When it is empty (older jobs), keep every eligible server.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from onyx.db.models import CraftJob, User
from onyx.server.features.build.jobs.channels import JobState
from onyx.skills.effective_mcp import resolve_effective_mcp_server_ids


def job_picker_selection(job: CraftJob) -> tuple[list[str], list[int]]:
    raw = job.state
    if not isinstance(raw, dict):
        return [], []
    try:
        state = JobState.model_validate(raw) if raw else JobState()
    except Exception:
        state = JobState()
    return list(state.selected_skill_ids or []), list(
        state.selected_mcp_server_ids or []
    )


def resolve_job_mcp_server_ids(
    db_session: Session,
    user: User,
    job: CraftJob,
) -> list[int] | None:
    """Turn allowlist for a job. ``None`` keeps every eligible server."""
    skill_ids, mcp_ids = job_picker_selection(job)
    if not skill_ids and not mcp_ids:
        return None
    return resolve_effective_mcp_server_ids(
        db_session,
        user,
        selected_mcp_server_ids=mcp_ids,
        selected_skill_ids=skill_ids,
    )
