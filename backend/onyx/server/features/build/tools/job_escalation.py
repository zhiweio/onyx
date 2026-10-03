"""Host-side ``start_long_job`` escalation: create the long job mid-turn.

The tool runs while the escalating interactive turn still holds the
session's active-turn lock, so the first (plan) phase turn is parked as a
pending enqueue and dispatched once that turn ends (see
``continuation.maybe_continue_craft_job``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from onyx.db.craft_job import get_specialist_for_session
from onyx.db.engine.sql_engine import get_session_with_current_tenant
from onyx.db.users import fetch_user_by_id
from onyx.error_handling.exceptions import OnyxError
from onyx.server.features.build.db.build_session import get_last_user_message
from onyx.server.features.build.tools.base import (
    ToolContext,
    ToolInvocation,
    ToolResult,
    text_result,
)
from onyx.server.features.build.tools.implementations import (
    StartJobHook,
    StartJobRequest,
)
from onyx.utils.logger import setup_logger

if TYPE_CHECKING:
    from onyx.db.models import User

logger = setup_logger()


def make_start_job_hook(owner: User) -> StartJobHook:
    """Bind the escalation to the bridge caller (the sandbox's owner)."""

    def _start_long_job(
        invocation: ToolInvocation,
        request: StartJobRequest,
        ctx: ToolContext,  # noqa: ARG001
    ) -> ToolResult:
        session_id = _invoked_session_id(invocation)
        if session_id is None:
            return text_result(
                "[start_long_job] no session in this call; "
                "escalate from the chat session"
            )
        try:
            with get_session_with_current_tenant() as db_session:
                user = fetch_user_by_id(db_session, owner.id)
                if user is None:
                    return text_result(
                        "[start_long_job] not started: calling user not found"
                    )
                if get_specialist_for_session(db_session, session_id) is not None:
                    return text_result(
                        "[start_long_job] not started: this session is a job "
                        "lane; escalate from the parent chat session"
                    )
                goal = request.goal or _latest_user_message_text(db_session, session_id)
                if not goal.strip():
                    return text_result(
                        "[start_long_job] not started: no goal. Pass 'goal' or "
                        "escalate right after the user's task message."
                    )
                from onyx.server.features.build.jobs.api import create_job_run
                from onyx.server.features.build.jobs.models import (
                    CraftJobCreateRequest,
                )

                create_job_run(
                    db_session,
                    user=user,
                    request=CraftJobCreateRequest(
                        session_id=session_id,
                        prompt=goal,
                        start=True,
                    ),
                )
        except OnyxError as exc:
            return text_result(f"[start_long_job] not started: {exc.detail}")
        except Exception as exc:
            logger.exception("start_long_job escalation failed")
            return text_result(f"[start_long_job] not started: {exc}")

        return text_result(
            "Long job started. The host owns every later turn: it will plan "
            "and run the phases on its own. Do not do the work yourself. "
            "Write one short user-visible line naming the goal and saying "
            "the deep task has started, then finish this turn."
        )

    return _start_long_job


def _invoked_session_id(invocation: ToolInvocation) -> UUID | None:
    if not invocation.session_id:
        return None
    try:
        return UUID(invocation.session_id)
    except ValueError:
        return None


def _latest_user_message_text(db_session: Any, session_id: UUID) -> str:
    message = get_last_user_message(session_id, db_session)
    if message is None:
        return ""
    metadata = message.message_metadata or {}
    content = metadata.get("content")
    if isinstance(content, dict) and isinstance(content.get("text"), str):
        return content["text"].strip()
    return ""
