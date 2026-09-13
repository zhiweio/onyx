"""Conversation activity for Craft Project session lists.

``BuildSession.status`` is sandbox lifecycle (ACTIVE means the workspace is
usable). The project page should match the Craft session view: running only
while a turn or long job is in flight.
"""

from __future__ import annotations

from uuid import UUID

from onyx.cache.interface import CacheBackend
from onyx.db.craft_job import OPEN_JOB_STATUSES
from onyx.db.enums import BuildSessionStatus, CraftJobStatus
from onyx.server.features.build.interactive_turns.state import get_active_turn


def project_session_activity_status(
    sandbox_status: BuildSessionStatus,
    *,
    job_status: CraftJobStatus | None,
    has_active_turn: bool = False,
) -> BuildSessionStatus:
    if sandbox_status == BuildSessionStatus.INITIALIZING:
        return BuildSessionStatus.INITIALIZING
    if sandbox_status == BuildSessionStatus.FAILED:
        return BuildSessionStatus.FAILED
    if has_active_turn or job_status in OPEN_JOB_STATUSES:
        return BuildSessionStatus.ACTIVE
    if job_status == CraftJobStatus.FAILED:
        return BuildSessionStatus.FAILED
    return BuildSessionStatus.IDLE


def session_ids_with_active_turns(
    cache: CacheBackend,
    user_id: UUID,
    session_ids: list[UUID],
) -> set[UUID]:
    active: set[UUID] = set()
    for session_id in session_ids:
        turn = get_active_turn(cache=cache, session_id=session_id, user_id=user_id)
        if turn is not None:
            active.add(session_id)
    return active
