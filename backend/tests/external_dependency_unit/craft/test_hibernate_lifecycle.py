"""Sandbox hibernation lifecycle (the Docker backend's scale lane).

The three-tier lifecycle: an idle sandbox is hibernated (runtime stopped,
kept for a fast wake), a long-asleep one is archived (snapshotted, runtime
destroyed), and the concurrency cap evicts idle sandboxes to make room.

Exercised through ``cleanup_idle_sandboxes_task`` and
``enforce_sandbox_concurrency`` against real Postgres + Redis; the backend
calls are routed through ``StubSandboxManager``. The sweep branches on
``supports_hibernation``, which the stub only reports when a test opts in —
the default (False) is the Kubernetes lane already covered by
``test_idle_cleanup.py``.
"""

from __future__ import annotations

import datetime
from collections.abc import Generator
from uuid import UUID

import pytest
from sqlalchemy import update
from sqlalchemy.orm import Session

from onyx.background.celery.tasks.build import tasks as tasks_module
from onyx.background.celery.tasks.build.tasks import cleanup_idle_sandboxes_task
from onyx.configs.constants import OnyxRedisLocks
from onyx.db.enums import BuildSessionStatus, SandboxStatus
from onyx.db.models import BuildSession, Sandbox, Snapshot, User
from onyx.redis.redis_pool import get_redis_client
from onyx.server.features.build.db.sandbox import (
    begin_provisioning_attempt__no_commit,
    finalize_provisioning_attempt__no_commit,
    hibernate_running_sandbox__no_commit,
)
from onyx.server.features.build.sandbox.models import SnapshotResult
from onyx.server.features.build.session import (
    sandbox_lifecycle as sandbox_lifecycle_module,
)
from onyx.server.features.build.session.errors import SandboxCapacityError
from onyx.server.features.build.session.sandbox_lifecycle import (
    enforce_sandbox_concurrency,
)
from shared_configs.configs import POSTGRES_DEFAULT_SCHEMA_STANDARD_VALUE
from tests.common.craft.stubs import StubSandboxManager
from tests.external_dependency_unit.craft.db_helpers import make_sandbox, make_user

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def hibernating_cleanup(
    stub_sandbox_manager: StubSandboxManager,
    monkeypatch: pytest.MonkeyPatch,
) -> StubSandboxManager:
    """Wire the stub as a hibernation-capable backend (the Docker lane)."""
    monkeypatch.setattr(
        tasks_module, "get_sandbox_manager", lambda: stub_sandbox_manager
    )
    stub_sandbox_manager.supports_hibernation = True
    stub_sandbox_manager.hibernate_silent = True
    stub_sandbox_manager.terminate_silent = True
    return stub_sandbox_manager


@pytest.fixture
def short_idle_threshold(monkeypatch: pytest.MonkeyPatch) -> int:
    """Lower the idle threshold so tests can backdate a heartbeat cheaply.

    The idle decision lives in the sandbox lifecycle (``is_sandbox_idle`` and
    the pre-stop re-check), so that is the module to patch. The task's
    background-snapshot cadence is its own config now
    (``SANDBOX_SNAPSHOT_INTERVAL_SECONDS``), so it needs no patch here.
    """
    threshold = 60
    monkeypatch.setattr(
        sandbox_lifecycle_module, "SANDBOX_IDLE_TIMEOUT_SECONDS", threshold
    )
    return threshold


@pytest.fixture
def short_hibernate_max_age(monkeypatch: pytest.MonkeyPatch) -> int:
    """Shorten the archive threshold so tests can backdate ``hibernated_at``."""
    seconds = 60
    monkeypatch.setattr(tasks_module, "SANDBOX_HIBERNATE_MAX_AGE_SECONDS", seconds)
    return seconds


@pytest.fixture(autouse=True)
def _quiesce_leaked_sandboxes(db_session: Session) -> None:
    """Terminate RUNNING sandboxes leaked by earlier tests.

    The sweep covers ALL RUNNING sandboxes globally, so rows committed by
    other tests in this directory would otherwise leak into our assertions.
    """
    db_session.execute(
        update(Sandbox)
        .where(Sandbox.status == SandboxStatus.RUNNING)
        .values(status=SandboxStatus.TERMINATED)
    )
    db_session.commit()


@pytest.fixture(autouse=True)
def _isolated_redis_lock() -> Generator[None, None, None]:
    """Make sure the cleanup beat lock is free before + after each test."""
    redis_client = get_redis_client(tenant_id=POSTGRES_DEFAULT_SCHEMA_STANDARD_VALUE)
    redis_client.delete(OnyxRedisLocks.CLEANUP_IDLE_SANDBOXES_BEAT_LOCK)
    try:
        yield
    finally:
        redis_client.delete(OnyxRedisLocks.CLEANUP_IDLE_SANDBOXES_BEAT_LOCK)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _backdate_heartbeat(
    db_session: Session, sandbox: Sandbox, seconds_ago: int
) -> None:
    sandbox.last_heartbeat = datetime.datetime.now(
        datetime.timezone.utc
    ) - datetime.timedelta(seconds=seconds_ago)
    db_session.flush()
    db_session.commit()


def _backdate_hibernated_at(
    db_session: Session, sandbox: Sandbox, seconds_ago: int
) -> None:
    sandbox.hibernated_at = datetime.datetime.now(
        datetime.timezone.utc
    ) - datetime.timedelta(seconds=seconds_ago)
    db_session.flush()
    db_session.commit()


def _run_sweep() -> None:
    cleanup_idle_sandboxes_task.run(
        tenant_id=POSTGRES_DEFAULT_SCHEMA_STANDARD_VALUE  # ty: ignore[invalid-argument-type]
    )


# ---------------------------------------------------------------------------
# Hibernation (idle lane)
# ---------------------------------------------------------------------------


def test_idle_sandbox_hibernated_instead_of_terminated(
    db_session: Session,
    test_user: User,  # noqa: ARG001
    hibernating_cleanup: StubSandboxManager,
    short_idle_threshold: int,
) -> None:
    """Idle sweep stops the runtime and keeps it; nothing is destroyed."""
    user = make_user(db_session)
    sandbox = make_sandbox(db_session, user)
    session_row = BuildSession(
        user_id=user.id,
        name="hibernate-session",
        status=BuildSessionStatus.ACTIVE,
        nextjs_port=3010,
    )
    db_session.add(session_row)
    db_session.commit()
    db_session.refresh(session_row)

    _backdate_heartbeat(db_session, sandbox, seconds_ago=short_idle_threshold * 4)

    hibernating_cleanup.supports_opencode_history_persistence = True
    hibernating_cleanup.create_opencode_history_snapshot_returns = True

    _run_sweep()

    db_session.expire_all()
    refreshed = db_session.get(Sandbox, sandbox.id)
    assert refreshed is not None
    assert refreshed.status == SandboxStatus.SLEEPING
    assert refreshed.hibernated_at is not None

    # The runtime was stopped, never destroyed, and no session workspace was
    # snapshotted — hibernation keeps the volume, so there is nothing to save.
    assert hibernating_cleanup.hibernated_sandbox_ids == [sandbox.id]
    assert hibernating_cleanup.terminated_sandbox_ids == []
    assert hibernating_cleanup.create_snapshot_count == 0

    # Chat history is captured before the stop so an unclean stop loses at
    # most seconds.
    assert {
        "sandbox_id": sandbox.id,
        "tenant_id": POSTGRES_DEFAULT_SCHEMA_STANDARD_VALUE,
        "timeout_seconds": 300.0,
    } in hibernating_cleanup.create_opencode_history_snapshot_payloads

    # The runtime is gone, so its ports and session activity are released.
    refreshed_session = db_session.get(BuildSession, session_row.id)
    assert refreshed_session is not None
    assert refreshed_session.status == BuildSessionStatus.IDLE
    assert refreshed_session.nextjs_port is None


def test_hibernate_history_snapshot_failure_still_hibernates(
    db_session: Session,
    test_user: User,  # noqa: ARG001
    hibernating_cleanup: StubSandboxManager,
    short_idle_threshold: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail-open: the writable layer survives the stop, so a failed history
    snapshot must not pin the sandbox RUNNING (unlike the archive lane)."""
    user = make_user(db_session)
    sandbox = make_sandbox(db_session, user)
    _backdate_heartbeat(db_session, sandbox, seconds_ago=short_idle_threshold * 4)

    hibernating_cleanup.supports_opencode_history_persistence = True

    def _boom(_sandbox_id: UUID, _tenant_id: str) -> bool:
        raise RuntimeError("history store unreachable")

    monkeypatch.setattr(hibernating_cleanup, "create_opencode_history_snapshot", _boom)

    _run_sweep()

    db_session.expire_all()
    refreshed = db_session.get(Sandbox, sandbox.id)
    assert refreshed is not None
    assert refreshed.status == SandboxStatus.SLEEPING
    assert refreshed.hibernated_at is not None
    assert hibernating_cleanup.hibernated_sandbox_ids == [sandbox.id]


def test_hibernate_failure_keeps_sandbox_running(
    db_session: Session,
    test_user: User,  # noqa: ARG001
    hibernating_cleanup: StubSandboxManager,
    short_idle_threshold: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stop that itself fails leaves the sandbox RUNNING for the next sweep."""
    user = make_user(db_session)
    sandbox = make_sandbox(db_session, user)
    _backdate_heartbeat(db_session, sandbox, seconds_ago=short_idle_threshold * 4)

    def _boom(_sandbox_id: UUID) -> None:
        raise RuntimeError("docker daemon unreachable")

    monkeypatch.setattr(hibernating_cleanup, "hibernate", _boom)

    _run_sweep()

    db_session.expire_all()
    refreshed = db_session.get(Sandbox, sandbox.id)
    assert refreshed is not None
    assert refreshed.status == SandboxStatus.RUNNING
    assert refreshed.hibernated_at is None


# ---------------------------------------------------------------------------
# Archive sweep (disk reclamation)
# ---------------------------------------------------------------------------


def test_archive_after_max_age_snapshots_and_destroys(
    db_session: Session,
    test_user: User,  # noqa: ARG001
    hibernating_cleanup: StubSandboxManager,
    short_hibernate_max_age: int,
) -> None:
    """A hibernated sandbox past the max age is snapshotted and destroyed."""
    user = make_user(db_session)
    sandbox = make_sandbox(db_session, user, status=SandboxStatus.SLEEPING)
    session_row = BuildSession(
        user_id=user.id,
        name="archive-session",
        status=BuildSessionStatus.IDLE,
    )
    db_session.add(session_row)
    db_session.commit()
    db_session.refresh(session_row)
    _backdate_hibernated_at(
        db_session, sandbox, seconds_ago=short_hibernate_max_age * 4
    )

    hibernating_cleanup.resume_stopped_runtime_returns = True
    hibernating_cleanup.list_session_workspaces_returns = [session_row.id]
    hibernating_cleanup.create_snapshot_returns = SnapshotResult(
        storage_path=f"s3://snapshots/{sandbox.id}/{session_row.id}.tar.gz",
        size_bytes=4321,
    )

    _run_sweep()

    db_session.expire_all()
    refreshed = db_session.get(Sandbox, sandbox.id)
    assert refreshed is not None
    # The row keeps the legacy SLEEPING meaning: runtime destroyed, snapshots
    # in FileStore — no hibernation claim left.
    assert refreshed.status == SandboxStatus.SLEEPING
    assert refreshed.hibernated_at is None

    assert hibernating_cleanup.resume_stopped_runtime_count == 1
    assert sandbox.id in hibernating_cleanup.terminated_sandbox_ids

    snapshots = (
        db_session.query(Snapshot).filter(Snapshot.session_id == session_row.id).all()
    )
    assert len(snapshots) >= 1
    assert all(s.size_bytes == 4321 for s in snapshots)


def test_archive_snapshot_failure_keeps_hibernation(
    db_session: Session,
    test_user: User,  # noqa: ARG001
    hibernating_cleanup: StubSandboxManager,
    short_hibernate_max_age: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail-closed: destroying an unsnapshotted workspace loses it, so a
    snapshot failure on a reachable runtime keeps the sandbox hibernated. The
    runtime the archive started is stopped again, so the retry holds no
    memory in the meantime."""
    user = make_user(db_session)
    sandbox = make_sandbox(db_session, user, status=SandboxStatus.SLEEPING)
    session_row = BuildSession(
        user_id=user.id,
        name="archive-fail-session",
        status=BuildSessionStatus.IDLE,
    )
    db_session.add(session_row)
    db_session.commit()
    db_session.refresh(session_row)
    _backdate_hibernated_at(
        db_session, sandbox, seconds_ago=short_hibernate_max_age * 4
    )
    hibernated_at_before = sandbox.hibernated_at

    hibernating_cleanup.resume_stopped_runtime_returns = True
    hibernating_cleanup.list_session_workspaces_returns = [session_row.id]
    hibernating_cleanup.health_check_returns = True

    def _boom(_sandbox_id: UUID, _session_id: UUID, _tenant_id: str) -> None:
        raise RuntimeError("S3 unreachable")

    monkeypatch.setattr(hibernating_cleanup, "create_snapshot", _boom)

    _run_sweep()

    db_session.expire_all()
    refreshed = db_session.get(Sandbox, sandbox.id)
    assert refreshed is not None
    assert refreshed.status == SandboxStatus.SLEEPING
    assert refreshed.hibernated_at == hibernated_at_before
    assert sandbox.id not in hibernating_cleanup.terminated_sandbox_ids
    # Aborting the archive re-stops the runtime it started.
    assert hibernating_cleanup.hibernated_sandbox_ids == [sandbox.id]


def test_archive_with_unstartable_runtime_still_destroys(
    db_session: Session,
    test_user: User,  # noqa: ARG001
    hibernating_cleanup: StubSandboxManager,
    short_hibernate_max_age: int,
) -> None:
    """A runtime that cannot start has an unrecoverable workspace; keeping it
    hibernated forever would only pin disk."""
    user = make_user(db_session)
    sandbox = make_sandbox(db_session, user, status=SandboxStatus.SLEEPING)
    _backdate_hibernated_at(
        db_session, sandbox, seconds_ago=short_hibernate_max_age * 4
    )

    hibernating_cleanup.resume_stopped_runtime_returns = False

    _run_sweep()

    db_session.expire_all()
    refreshed = db_session.get(Sandbox, sandbox.id)
    assert refreshed is not None
    assert refreshed.status == SandboxStatus.SLEEPING
    assert refreshed.hibernated_at is None
    assert sandbox.id in hibernating_cleanup.terminated_sandbox_ids


# ---------------------------------------------------------------------------
# Concurrency cap (eviction)
# ---------------------------------------------------------------------------


@pytest.fixture
def cap_of_two(monkeypatch: pytest.MonkeyPatch) -> int:
    cap = 2
    monkeypatch.setattr(sandbox_lifecycle_module, "SANDBOX_MAX_CONCURRENT", cap)
    return cap


def test_cap_evicts_least_recently_active_idle_sandbox(
    db_session: Session,
    test_user: User,  # noqa: ARG001
    stub_sandbox_manager: StubSandboxManager,
    short_idle_threshold: int,
    cap_of_two: int,
) -> None:
    """At the cap, the least-recently-active idle sandbox is hibernated so the
    caller's provision can proceed."""
    manager = stub_sandbox_manager
    manager.supports_hibernation = True
    manager.hibernate_silent = True

    victim_user = make_user(db_session)
    victim = make_sandbox(db_session, victim_user)
    _backdate_heartbeat(db_session, victim, seconds_ago=short_idle_threshold * 10)

    requester_user = make_user(db_session)

    # Two running sandboxes: the cap's headroom.
    manager.count_active_sandboxes_returns = cap_of_two

    enforce_sandbox_concurrency(
        db_session,
        manager,
        POSTGRES_DEFAULT_SCHEMA_STANDARD_VALUE,
        excluding_user_id=requester_user.id,
    )

    db_session.expire_all()
    refreshed = db_session.get(Sandbox, victim.id)
    assert refreshed is not None
    assert refreshed.status == SandboxStatus.SLEEPING
    assert refreshed.hibernated_at is not None
    assert manager.hibernated_sandbox_ids == [victim.id]


def test_cap_raises_capacity_error_when_nothing_evictable(
    db_session: Session,
    test_user: User,  # noqa: ARG001
    stub_sandbox_manager: StubSandboxManager,
    short_idle_threshold: int,
    cap_of_two: int,
) -> None:
    """Active sandboxes are never evicted; the caller gets a capacity error."""
    manager = stub_sandbox_manager
    manager.supports_hibernation = True
    manager.hibernate_silent = True

    busy_user = make_user(db_session)
    busy_sandbox = make_sandbox(db_session, busy_user)
    # Fresh heartbeat: active, not a candidate.
    _backdate_heartbeat(db_session, busy_sandbox, seconds_ago=short_idle_threshold // 2)

    requester_user = make_user(db_session)
    manager.count_active_sandboxes_returns = cap_of_two

    with pytest.raises(SandboxCapacityError):
        enforce_sandbox_concurrency(
            db_session,
            manager,
            POSTGRES_DEFAULT_SCHEMA_STANDARD_VALUE,
            excluding_user_id=requester_user.id,
        )

    db_session.expire_all()
    refreshed = db_session.get(Sandbox, busy_sandbox.id)
    assert refreshed is not None
    assert refreshed.status == SandboxStatus.RUNNING
    assert manager.hibernated_sandbox_ids == []


def test_cap_does_not_evict_the_requesting_users_own_sandbox(
    db_session: Session,
    test_user: User,  # noqa: ARG001
    stub_sandbox_manager: StubSandboxManager,
    short_idle_threshold: int,
    cap_of_two: int,
) -> None:
    """The user's own (already running) sandbox is never the victim."""
    manager = stub_sandbox_manager
    manager.supports_hibernation = True
    manager.hibernate_silent = True

    requester_user = make_user(db_session)
    own_sandbox = make_sandbox(db_session, requester_user)
    _backdate_heartbeat(db_session, own_sandbox, seconds_ago=short_idle_threshold * 10)
    manager.count_active_sandboxes_returns = cap_of_two

    with pytest.raises(SandboxCapacityError):
        enforce_sandbox_concurrency(
            db_session,
            manager,
            POSTGRES_DEFAULT_SCHEMA_STANDARD_VALUE,
            excluding_user_id=requester_user.id,
        )

    db_session.expire_all()
    refreshed = db_session.get(Sandbox, own_sandbox.id)
    assert refreshed is not None
    assert refreshed.status == SandboxStatus.RUNNING


def test_cap_noop_within_headroom(
    db_session: Session,
    test_user: User,  # noqa: ARG001
    stub_sandbox_manager: StubSandboxManager,
    cap_of_two: int,
) -> None:
    """Below the cap nothing is touched."""
    manager = stub_sandbox_manager
    manager.supports_hibernation = True
    manager.count_active_sandboxes_returns = cap_of_two - 1

    requester_user = make_user(db_session)
    enforce_sandbox_concurrency(
        db_session,
        manager,
        POSTGRES_DEFAULT_SCHEMA_STANDARD_VALUE,
        excluding_user_id=requester_user.id,
    )

    assert manager.hibernated_sandbox_ids == []
    assert manager.count_active_sandboxes_returns == cap_of_two - 1


# ---------------------------------------------------------------------------
# Status transitions
# ---------------------------------------------------------------------------


def test_finalize_running_clears_hibernation_claim(
    db_session: Session,
    test_user: User,  # noqa: ARG001
) -> None:
    """The wake path (SLEEPING -> PROVISIONING -> RUNNING) drops the claim, so
    an archive sweep can no longer act on the runtime it now owns."""
    user = make_user(db_session)
    sandbox = make_sandbox(db_session, user)

    assert hibernate_running_sandbox__no_commit(db_session, sandbox.id, 0)
    db_session.commit()
    db_session.expire_all()
    hibernated = db_session.get(Sandbox, sandbox.id)
    assert hibernated is not None
    assert hibernated.status == SandboxStatus.SLEEPING
    assert hibernated.hibernated_at is not None

    attempt = begin_provisioning_attempt__no_commit(db_session, hibernated)
    db_session.commit()
    assert finalize_provisioning_attempt__no_commit(
        db_session, sandbox.id, attempt, SandboxStatus.RUNNING
    )
    db_session.commit()

    db_session.expire_all()
    refreshed = db_session.get(Sandbox, sandbox.id)
    assert refreshed is not None
    assert refreshed.status == SandboxStatus.RUNNING
    assert refreshed.hibernated_at is None


def test_hibernate_cas_loses_to_newer_attempt(
    db_session: Session,
    test_user: User,  # noqa: ARG001
) -> None:
    """A stale attempt's hibernate write is a no-op, so a wake that took over
    the row is never clobbered."""
    user = make_user(db_session)
    sandbox = make_sandbox(db_session, user)
    stale_attempt = sandbox.provisioning_attempt_number
    attempt = begin_provisioning_attempt__no_commit(db_session, sandbox)
    db_session.commit()
    assert attempt == stale_attempt + 1

    assert not hibernate_running_sandbox__no_commit(
        db_session, sandbox.id, stale_attempt
    )
