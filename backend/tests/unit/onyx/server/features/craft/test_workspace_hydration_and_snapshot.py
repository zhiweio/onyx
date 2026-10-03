"""WS2 guards: hydration marker blocks torn workspaces; teardown snapshots
never run while a turn is active."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from uuid import uuid4

from onyx.db.enums import BuildSessionStatus
from onyx.db.models import BuildSession, Sandbox
from onyx.server.features.build.session.session_ready import session_runtime_intact


def _session(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "status": BuildSessionStatus.ACTIVE,
        "workspace_hydration_pending": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _sandbox() -> SimpleNamespace:
    return SimpleNamespace(status=SimpleNamespace(is_active=lambda: True))


def test_runtime_intact_requires_active_session_and_healthy_sandbox() -> None:
    assert (
        session_runtime_intact(
            cast(BuildSession, _session()), cast(Sandbox, _sandbox())
        )
        is True
    )


def test_runtime_intact_rejects_pending_hydration() -> None:
    session = cast(BuildSession, _session(workspace_hydration_pending=True))
    assert session_runtime_intact(session, cast(Sandbox, _sandbox())) is False


def test_runtime_intact_rejects_missing_parts() -> None:
    assert session_runtime_intact(None, cast(Sandbox, _sandbox())) is False
    assert session_runtime_intact(cast(BuildSession, _session()), None) is False


class _NullSession:
    def __enter__(self) -> object:
        return SimpleNamespace()

    def __exit__(self, *_a: object) -> bool:
        return False


def _patch_executor_db(monkeypatch) -> None:
    monkeypatch.setattr(
        "onyx.server.features.build.interactive_turns.executor.get_cache_backend",
        lambda **_k: SimpleNamespace(),
    )
    monkeypatch.setattr(
        "onyx.server.features.build.interactive_turns.executor."
        "get_session_with_current_tenant",
        lambda: _NullSession(),
    )
    monkeypatch.setattr(
        "onyx.server.features.build.interactive_turns.executor.get_sandbox_manager",
        lambda: SimpleNamespace(),
    )


def test_teardown_snapshot_skips_session_with_active_turn(monkeypatch) -> None:
    from onyx.server.features.build.interactive_turns import executor

    snapshots: list[tuple[object, object]] = []
    _patch_executor_db(monkeypatch)
    monkeypatch.setattr(
        "onyx.server.features.build.interactive_turns.executor.get_active_turn",
        lambda **_k: SimpleNamespace(turn_id=uuid4()),
    )
    monkeypatch.setattr(
        "onyx.server.features.build.session.sandbox_lifecycle."
        "create_session_snapshot_keep_latest",
        lambda _m, _d, sandbox_id, session_id, _t: snapshots.append(
            (sandbox_id, session_id)
        ),
    )
    thread = executor._snapshot_session_workspace_after_turn(
        sandbox_id=uuid4(),
        session_id=uuid4(),
        user_id=uuid4(),
        tenant_id=None,
    )
    thread.join(timeout=5)
    assert snapshots == []


def test_teardown_snapshot_runs_for_quiet_session(monkeypatch) -> None:
    from onyx.server.features.build.interactive_turns import executor

    snapshots: list[tuple[object, object]] = []
    _patch_executor_db(monkeypatch)
    monkeypatch.setattr(
        "onyx.server.features.build.interactive_turns.executor.get_active_turn",
        lambda **_k: None,
    )
    monkeypatch.setattr(
        "onyx.server.features.build.session.sandbox_lifecycle."
        "create_session_snapshot_keep_latest",
        lambda _m, _d, sandbox_id, session_id, _t: snapshots.append(
            (sandbox_id, session_id)
        ),
    )
    sandbox_id = uuid4()
    session_id = uuid4()
    thread = executor._snapshot_session_workspace_after_turn(
        sandbox_id=sandbox_id,
        session_id=session_id,
        user_id=uuid4(),
        tenant_id=None,
    )
    thread.join(timeout=5)
    assert snapshots == [(sandbox_id, session_id)]


def test_teardown_snapshot_skips_untouched_session_with_existing_snapshot(
    monkeypatch,
) -> None:
    """A turn that ran no tool left the workspace unchanged, so an existing
    snapshot still matches and the archive is skipped (qm: homeUnchanged)."""
    from onyx.server.features.build.interactive_turns import executor

    snapshots: list[tuple[object, object]] = []
    _patch_executor_db(monkeypatch)
    monkeypatch.setattr(
        "onyx.server.features.build.interactive_turns.executor.get_active_turn",
        lambda **_k: None,
    )
    monkeypatch.setattr(
        "onyx.server.features.build.db.sandbox.get_snapshots_for_session",
        lambda *_a, **_k: [SimpleNamespace()],
    )
    monkeypatch.setattr(
        "onyx.server.features.build.session.sandbox_lifecycle."
        "create_session_snapshot_keep_latest",
        lambda _m, _d, sandbox_id, session_id, _t: snapshots.append(
            (sandbox_id, session_id)
        ),
    )
    thread = executor._snapshot_session_workspace_after_turn(
        sandbox_id=uuid4(),
        session_id=uuid4(),
        user_id=uuid4(),
        tenant_id=None,
        workspace_touched=False,
    )
    thread.join(timeout=5)
    assert snapshots == []


def test_teardown_snapshot_runs_for_untouched_session_without_snapshot(
    monkeypatch,
) -> None:
    """No prior snapshot (first turn, or every snapshot was pruned): archive
    even when the workspace is untouched, so sleep/restore still has a base."""
    from onyx.server.features.build.interactive_turns import executor

    snapshots: list[tuple[object, object]] = []
    _patch_executor_db(monkeypatch)
    monkeypatch.setattr(
        "onyx.server.features.build.interactive_turns.executor.get_active_turn",
        lambda **_k: None,
    )
    monkeypatch.setattr(
        "onyx.server.features.build.db.sandbox.get_snapshots_for_session",
        lambda *_a, **_k: [],
    )
    monkeypatch.setattr(
        "onyx.server.features.build.session.sandbox_lifecycle."
        "create_session_snapshot_keep_latest",
        lambda _m, _d, sandbox_id, session_id, _t: snapshots.append(
            (sandbox_id, session_id)
        ),
    )
    sandbox_id = uuid4()
    session_id = uuid4()
    thread = executor._snapshot_session_workspace_after_turn(
        sandbox_id=sandbox_id,
        session_id=session_id,
        user_id=uuid4(),
        tenant_id=None,
        workspace_touched=False,
    )
    thread.join(timeout=5)
    assert snapshots == [(sandbox_id, session_id)]
