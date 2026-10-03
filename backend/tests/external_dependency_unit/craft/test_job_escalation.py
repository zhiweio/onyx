"""start_long_job escalation: mid-turn job creation and deferred dispatch.

The platform tool runs while the escalating interactive turn holds the
session's active-turn lock, so the job's first (plan) phase turn is parked
as a pending enqueue and dispatched by the post-turn continuation.
"""

from __future__ import annotations

from typing import Callable
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from onyx.cache.factory import get_cache_backend
from onyx.configs.constants import MessageType
from onyx.db.craft_job import get_open_job_for_session
from onyx.db.enums import BuildSessionStatus, CraftJobStatus, SandboxStatus
from onyx.db.models import BuildSession, CraftJob, Sandbox, User
from onyx.server.features.build.db.build_session import create_message
from onyx.server.features.build.interactive_turns.state import (
    acquire_active_turn_lock,
    get_active_turn,
)
from onyx.server.features.build.jobs.continuation import maybe_continue_craft_job
from onyx.server.features.build.jobs.protocol import current_phase
from onyx.server.features.build.tools.base import ToolContext, ToolInvocation
from onyx.server.features.build.tools.implementations import StartJobRequest
from onyx.server.features.build.tools.job_escalation import make_start_job_hook
from shared_configs.configs import POSTGRES_DEFAULT_SCHEMA_STANDARD_VALUE
from tests.common.craft.stubs import StubSandboxManager


def _make_session(
    db_session: Session,
    user: User,
    sandbox: Callable[..., Sandbox],
) -> tuple[BuildSession, UUID]:
    row = sandbox(user=user, status=SandboxStatus.RUNNING)
    session = BuildSession(
        id=uuid4(),
        user_id=user.id,
        name="escalation",
        status=BuildSessionStatus.ACTIVE,
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    return session, row.id


def _escalate(user: User, session: BuildSession, goal: str = ""):
    hook = make_start_job_hook(user)
    return hook(
        ToolInvocation(
            tool="start_long_job",
            arguments={"goal": goal} if goal else {},
            session_id=str(session.id),
        ),
        StartJobRequest(goal),
        ToolContext(user_id=str(user.id)),
    )


def _add_user_message(db_session: Session, session: BuildSession, text: str) -> None:
    create_message(
        session_id=session.id,
        message_type=MessageType.USER,
        turn_index=0,
        message_metadata={
            "type": "user_message",
            "content": {"type": "text", "text": text},
        },
        db_session=db_session,
    )
    db_session.commit()


def test_escalation_creates_job_and_defers_plan_turn(
    db_session: Session,
    test_user: User,
    tenant_context: None,  # noqa: ARG001
    sandbox: Callable[..., Sandbox],
    stub_sandbox_manager: StubSandboxManager,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "onyx.server.features.build.sandbox.factory._sandbox_manager_instance",
        stub_sandbox_manager,
    )
    session, sandbox_id = _make_session(db_session, test_user, sandbox)
    _add_user_message(db_session, session, "Write the Q3 financial report")
    cache = get_cache_backend(tenant_id=POSTGRES_DEFAULT_SCHEMA_STANDARD_VALUE)

    # The escalating plain turn still holds the active-turn lock.
    lock = acquire_active_turn_lock(cache, session.id)
    result = _escalate(test_user, session)

    assert result.text().startswith("Long job started")
    job = get_open_job_for_session(db_session, session.id)
    assert job is not None
    assert job.status == CraftJobStatus.RUNNING
    phase = current_phase(job.phases, job.current_phase_index)
    assert phase is not None
    parked = phase.get("pending_enqueue_prompt")
    assert isinstance(parked, str)
    assert "Write the Q3 financial report" in parked
    # The turn lock is still held: no plan turn was dispatched yet.
    assert (
        get_active_turn(cache=cache, session_id=session.id, user_id=test_user.id)
        is None
    )

    lock.release()
    maybe_continue_craft_job(
        db_session,
        session_id=session.id,
        user_id=test_user.id,
        sandbox_id=sandbox_id,
        turn_succeeded=True,
        deadline_exceeded=False,
        cancelled=False,
    )
    assert (
        get_active_turn(cache=cache, session_id=session.id, user_id=test_user.id)
        is not None
    )
    db_session.expire_all()
    job = get_open_job_for_session(db_session, session.id)
    assert job is not None
    phase = current_phase(job.phases, job.current_phase_index)
    assert phase is not None
    assert not phase.get("pending_enqueue_prompt")


def test_second_escalation_while_job_open_reports_error(
    db_session: Session,
    test_user: User,
    tenant_context: None,  # noqa: ARG001
    sandbox: Callable[..., Sandbox],
    stub_sandbox_manager: StubSandboxManager,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "onyx.server.features.build.sandbox.factory._sandbox_manager_instance",
        stub_sandbox_manager,
    )
    session, _ = _make_session(db_session, test_user, sandbox)
    _add_user_message(db_session, session, "Write the annual review")
    cache = get_cache_backend(tenant_id=POSTGRES_DEFAULT_SCHEMA_STANDARD_VALUE)

    lock = acquire_active_turn_lock(cache, session.id)
    try:
        first = _escalate(test_user, session)
        second = _escalate(test_user, session)
    finally:
        lock.release()

    assert first.text().startswith("Long job started")
    assert "not started" in second.text()
    # Exactly one open job despite the double escalation.
    assert (
        db_session.query(CraftJob)
        .filter(
            CraftJob.session_id == session.id,
            CraftJob.status.in_([CraftJobStatus.PENDING, CraftJobStatus.RUNNING]),
        )
        .count()
        == 1
    )
