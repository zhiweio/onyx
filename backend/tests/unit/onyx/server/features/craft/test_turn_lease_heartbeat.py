"""The per-turn job lease heartbeat: renew while alive, self-report when lost."""

from __future__ import annotations

import threading
from types import SimpleNamespace
from uuid import uuid4

from onyx.db.enums import CraftJobStatus
from onyx.server.features.build.interactive_turns.executor import (
    CRAFT_JOB_LEASE_MAX_MISSED_BEATS,
    _hold_job_lease,
)


class _FakeSession:
    def __init__(self, job: SimpleNamespace | None) -> None:
        self.job = job
        self.commits = 0

    def __enter__(self) -> "_FakeSession":
        return self

    def __exit__(self, *_a: object) -> bool:
        return False

    def get(self, _model: type, _job_id: object) -> SimpleNamespace | None:
        return self.job

    def commit(self) -> None:
        self.commits += 1


class _StopAfter(threading.Event):
    """Event stand-in: `wait` runs `beats` beats, then reports the stop."""

    def __init__(self, beats: int) -> None:
        super().__init__()
        self.remaining = beats

    def wait(self, timeout: float | None = None) -> bool:  # noqa: ARG002
        self.remaining -= 1
        return self.remaining < 0


def _job() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        status=CraftJobStatus.RUNNING,
        lease_owner="turn-1",
        lease_expires_at=None,
    )


def test_heartbeat_renews_lease_until_stopped(monkeypatch) -> None:
    job = _job()
    beats: list[tuple[str, int]] = []
    monkeypatch.setattr(
        "onyx.server.features.build.interactive_turns.executor."
        "get_session_with_current_tenant",
        lambda: _FakeSession(job),
    )
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.kernel.renew_lease",
        lambda j, *, owner, seconds: beats.append((owner, seconds)),  # noqa: ARG005
    )
    stop = _StopAfter(beats=2)
    lease_lost = threading.Event()
    _hold_job_lease(job.id, "turn-1", stop, lease_lost, tenant_id=None)
    assert len(beats) == 2
    assert all(owner == "turn-1" for owner, _seconds in beats)
    assert lease_lost.is_set() is False


def test_heartbeat_reports_loss_after_consecutive_failures(monkeypatch) -> None:
    job = _job()
    monkeypatch.setattr(
        "onyx.server.features.build.interactive_turns.executor."
        "get_session_with_current_tenant",
        lambda: _FakeSession(job),
    )

    def _raise(*_a: object, **_k: object) -> None:
        raise RuntimeError("db down")

    monkeypatch.setattr("onyx.server.features.build.jobs.kernel.renew_lease", _raise)
    stop = _StopAfter(beats=CRAFT_JOB_LEASE_MAX_MISSED_BEATS + 1)
    lease_lost = threading.Event()
    _hold_job_lease(job.id, "turn-1", stop, lease_lost, tenant_id=None)
    assert lease_lost.is_set() is True


def test_heartbeat_stops_for_terminal_job(monkeypatch) -> None:
    job = _job()
    job.status = CraftJobStatus.FAILED
    session = _FakeSession(job)
    monkeypatch.setattr(
        "onyx.server.features.build.interactive_turns.executor."
        "get_session_with_current_tenant",
        lambda: session,
    )
    monkeypatch.setattr(
        "onyx.server.features.build.jobs.kernel.renew_lease",
        lambda *_a, **_k: None,
    )
    stop = _StopAfter(beats=3)
    lease_lost = threading.Event()
    _hold_job_lease(job.id, "turn-1", stop, lease_lost, tenant_id=None)
    assert lease_lost.is_set() is False
