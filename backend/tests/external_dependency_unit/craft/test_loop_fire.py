"""External-dependency tests for the craft loop fire machinery.

Drives ``loops_fire_sweep_logic`` and ``run_loop_item_logic`` against
real Postgres with the stub sandbox manager (same pattern as the
scheduled-task executor suite).
"""

from collections.abc import Generator
from typing import Any

import pytest
from sqlalchemy.orm import Session

from onyx.db.craft_loop import (
    create_craft_loop,
    enqueue_loop_items,
    get_craft_loop,
    get_loop_item,
    list_loop_items,
)
from onyx.db.enums import (
    CraftLoopHealth,
    CraftLoopItemStatus,
    CraftLoopOutputState,
    CraftLoopState,
    SandboxStatus,
)
from onyx.db.models import CraftLoopOutput, Sandbox, User
from onyx.server.features.build.loops.fire import (
    loops_fire_sweep_logic,
    run_loop_item_logic,
)
from onyx.server.features.build.sandbox.event_schema import (
    Error,
    PromptResponse,
)
from onyx.server.features.build.session.manager import SessionManager
from tests.common.craft.stubs import StubSandboxManager

from tests.external_dependency_unit.craft.conftest import *  # noqa: F401,F403


def _seed_loop(
    db_session: Session,
    user: User,
    *,
    cron: str = "* * * * *",
    ship_actions: list[dict] | None = None,
) -> Any:
    loop = create_craft_loop(
        db_session,
        user_id=user.id,
        name="测试循环",
        playbook={"objective": "整理条目", "deliverables": ["outputs/report.md"]},
        ship_actions=ship_actions or [{"action": "save_artifacts", "gate": "hold"}],
        trigger_cron=cron,
    )
    db_session.commit()
    return loop


_STUB_SILENT_ATTRS = (
    "health_check_returns",
    "setup_session_workspace_silent",
    "write_sandbox_file_silent",
    "write_files_to_sandbox_silent",
    "regenerate_session_config_silent",
    "dispose_opencode_instance_silent",
)


def _silence_stub(stub: StubSandboxManager) -> None:
    stub.health_check_returns = True
    for attr in _SILENT_ATTRS:
        setattr(stub, attr, True)


def _patch_skills_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "onyx.server.features.build.session.sandbox_lifecycle.build_user_skills_payload",
        lambda *_: ("", {}),
    )


def _patch_artifacts(
    monkeypatch: pytest.MonkeyPatch, paths: list[str]
) -> None:
    """Stub the durable artifact catalog the executor stages outputs from."""
    monkeypatch.setattr(
        SessionManager,
        "list_artifacts",
        lambda self, session_id, user_id: [
            {"name": p.split("/")[-1], "path": p, "type": "file"} for p in paths
        ],
    )


# ── sweep ─────────────────────────────────────────────────────────────────


def test_sweep_claims_due_loop_and_items(
    db_session: Session, test_user: User
) -> None:
    loop = _seed_loop(db_session, test_user)
    loop.next_fire_at = None  # due immediately
    from datetime import datetime, timedelta, timezone

    loop.next_fire_at = datetime.now(timezone.utc) - timedelta(seconds=5)
    enqueue_loop_items(
        db_session,
        loop.id,
        [{"source_key": "fact-1", "summary": "第一条"}, {"source_key": "fact-2"}],
    )
    db_session.commit()

    manifest = loops_fire_sweep_logic()

    assert len(manifest) == 2
    assert {m["item_id"] for m in manifest} == {
        str(item.id) for item in list_loop_items(db_session, loop.id)
    }
    db_session.expire_all()
    refreshed = get_craft_loop(db_session, loop.id)
    assert refreshed is not None
    # advanced beyond now
    assert refreshed.next_fire_at is not None
    items = list_loop_items(db_session, loop.id)
    assert all(i.status is CraftLoopItemStatus.IN_PROGRESS for i in items)
    assert all(i.attempts == 1 for i in items)


def test_sweep_skips_not_due_and_capped(
    db_session: Session, test_user: User
) -> None:
    from datetime import datetime, timedelta, timezone

    loop = _seed_loop(db_session, test_user)
    loop.next_fire_at = datetime.now(timezone.utc) + timedelta(minutes=30)
    db_session.commit()
    assert loops_fire_sweep_logic() == []

    # due again, but cap = 1
    loop = get_craft_loop(db_session, loop.id)
    loop.next_fire_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    loop.caps = {"max_items_per_fire": 1}
    db_session.commit()
    enqueue_loop_items(
        db_session,
        loop.id,
        [{"source_key": "a"}, {"source_key": "b"}],
    )
    db_session.commit()
    assert len(loops_fire_sweep_logic()) == 1


def test_sweep_requeues_expired_claims(
    db_session: Session, test_user: User
) -> None:
    from datetime import datetime, timedelta, timezone

    loop = _seed_loop(db_session, test_user)
    items = enqueue_loop_items(db_session, loop.id, [{"source_key": "stale"}])
    item = items[0]
    item.status = CraftLoopItemStatus.IN_PROGRESS
    item.claim_token = "dead"
    item.claim_expires_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    loop.next_fire_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()

    manifest = loops_fire_sweep_logic()

    # requeued then immediately re-claimed by the sweep itself
    assert len(manifest) == 1
    db_session.expire_all()
    refreshed = get_loop_item(db_session, item.id)
    assert refreshed is not None
    assert refreshed.status is CraftLoopItemStatus.IN_PROGRESS
    assert refreshed.claim_token != "dead"
    assert refreshed.attempts == 2  # first attempt was the stale one


# ── item executor ─────────────────────────────────────────────────────────


def test_item_success_hold_gate_parks_output(
    db_session: Session,
    test_user: User,
    sandbox: Any,
    stub_sandbox_manager: StubSandboxManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_skills_payload(monkeypatch)
    monkeypatch.setattr(
        "onyx.server.features.build.session.manager.get_sandbox_manager",
        lambda: stub_sandbox_manager,
    )
    sandbox(user=test_user, status=SandboxStatus.RUNNING)
    loop = _seed_loop(db_session, test_user, ship_actions=[{"action": "save_artifacts", "gate": "hold"}])
    items = enqueue_loop_items(db_session, loop.id, [{"source_key": "f1", "summary": "事实"}])
    db_session.commit()

    _silence_stub(stub_sandbox_manager)
    stub_sandbox_manager.send_message_events = [
        PromptResponse.model_validate({"stopReason": "end_turn"}),
    ]
    _patch_artifacts(monkeypatch, ["outputs/report.md"])

    token = loops_fire_sweep_logic()
    manifest = [m for m in token if m["item_id"] == str(items[0].id)]
    assert manifest
    run_loop_item_logic(items[0].id, claim_token=manifest[0]["claim_token"])

    db_session.expire_all()
    item = get_loop_item(db_session, items[0].id)
    assert item is not None
    assert item.status is CraftLoopItemStatus.READY
    outputs = db_session.query(CraftLoopOutput).all()
    assert len(outputs) == 1
    assert outputs[0].state is CraftLoopOutputState.READY  # held for review


def test_item_success_auto_gate_ships(
    db_session: Session,
    test_user: User,
    sandbox: Any,
    stub_sandbox_manager: StubSandboxManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_skills_payload(monkeypatch)
    monkeypatch.setattr(
        "onyx.server.features.build.session.manager.get_sandbox_manager",
        lambda: stub_sandbox_manager,
    )
    sandbox(user=test_user, status=SandboxStatus.RUNNING)
    loop = _seed_loop(db_session, test_user, ship_actions=[{"action": "save_artifacts", "gate": "auto"}])
    items = enqueue_loop_items(db_session, loop.id, [{"source_key": "f2"}])
    db_session.commit()

    _silence_stub(stub_sandbox_manager)
    stub_sandbox_manager.send_message_events = [
        PromptResponse.model_validate({"stopReason": "end_turn"}),
    ]
    _patch_artifacts(monkeypatch, ["outputs/report.md"])

    manifest = [m for m in loops_fire_sweep_logic() if m["item_id"] == str(items[0].id)]
    run_loop_item_logic(items[0].id, claim_token=manifest[0]["claim_token"])

    db_session.expire_all()
    outputs = db_session.query(CraftLoopOutput).all()
    assert len(outputs) == 1
    assert outputs[0].state is CraftLoopOutputState.SHIPPED
    item = get_loop_item(db_session, items[0].id)
    assert item is not None
    assert item.status is CraftLoopItemStatus.READY


def test_item_failure_retries_then_parks_and_governor_quarantines(
    db_session: Session,
    test_user: User,
    sandbox: Any,
    stub_sandbox_manager: StubSandboxManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_skills_payload(monkeypatch)
    monkeypatch.setattr(
        "onyx.server.features.build.session.manager.get_sandbox_manager",
        lambda: stub_sandbox_manager,
    )
    sandbox(user=test_user, status=SandboxStatus.RUNNING)
    loop = _seed_loop(db_session, test_user)
    items = enqueue_loop_items(db_session, loop.id, [{"source_key": "f3"}])
    db_session.commit()
    item_id = items[0].id

    _silence_stub(stub_sandbox_manager)
    stub_sandbox_manager.send_message_events = [
        Error.model_validate({"code": "agent_error", "message": "boom"}),
    ]

    # three consecutive failures → parked + quarantined
    for _ in range(3):
        manifest = [m for m in loops_fire_sweep_logic() if m["item_id"] == str(item_id)]
        if not manifest:
            # loop quarantined already; requeue by hand for the next attempt
            db_session.expire_all()
            item = get_loop_item(db_session, item_id)
            assert item is not None
            if item.status is CraftLoopItemStatus.FAILED:
                break
            continue
        run_loop_item_logic(item_id, claim_token=manifest[0]["claim_token"])

    db_session.expire_all()
    item = get_loop_item(db_session, item_id)
    assert item is not None
    assert item.status is CraftLoopItemStatus.FAILED
    loop_row = get_craft_loop(db_session, loop.id)
    assert loop_row is not None
    assert loop_row.health is CraftLoopHealth.QUARANTINED
    assert loop_row.state is CraftLoopState.QUARANTINED
    # quarantined loops are never swept again
    assert loops_fire_sweep_logic() == []


def test_stale_claim_token_is_noop(
    db_session: Session,
    test_user: User,
    sandbox: Any,  # noqa: ARG001
) -> None:
    sandbox(user=test_user, status=SandboxStatus.RUNNING)
    loop = _seed_loop(db_session, test_user)
    items = enqueue_loop_items(db_session, loop.id, [{"source_key": "f4"}])
    db_session.commit()
    run_loop_item_logic(items[0].id, claim_token="not-the-token")
    db_session.expire_all()
    item = get_loop_item(db_session, items[0].id)
    assert item is not None
    assert item.status is CraftLoopItemStatus.QUEUED
    assert item.attempts == 0
