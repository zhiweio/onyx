"""Unit tests for the craft loop core: ledger machine, ship gate, governor."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from onyx.db.enums import (
    CraftLoopHealth,
    CraftLoopItemStatus,
    CraftLoopOutputState,
    CraftLoopState,
    ShipGate,
)
from onyx.db.models import CraftLoop, CraftLoopGrant, CraftLoopItem, CraftLoopOutput
from onyx.server.features.build.loops.core import (
    LedgerTransitionError,
    assert_transition,
    bump_policy_version,
    claim_item,
    decide_ship,
    evaluate_governor,
    graduate,
    grant_covers,
    mark_ready,
    record_work_failure,
    release_expired_claims,
    return_to_work,
    set_autopilot,
    ship_gate_for_action,
)

NOW = datetime(2026, 9, 30, tzinfo=timezone.utc)
USER = UUID(int=1)


def _loop(ship_actions: list[dict] | None = None, policy_version: int = 1) -> CraftLoop:
    return CraftLoop(
        user_id=USER,
        name="季度风控扫描",
        policy_version=policy_version,
        ship_actions=ship_actions
        or [
            {"action": "save_artifacts", "gate": "hold"},
            {"action": "notify_im", "gate": "hold"},
        ],
        state=CraftLoopState.ENABLED,
        health=CraftLoopHealth.HEALTHY,
        consecutive_failed_fires=0,
    )


def _item(status: CraftLoopItemStatus = CraftLoopItemStatus.QUEUED) -> CraftLoopItem:
    return CraftLoopItem(
        loop_id=UUID(int=2),
        source_key="invoice-2026q3-001",
        status=status,
        attempts=0,
        proposal={},
    )


def _output(
    action: str = "save_artifacts", label: str | None = None
) -> CraftLoopOutput:
    return CraftLoopOutput(
        loop_id=UUID(int=2),
        item_id=UUID(int=3),
        ship_action=action,
        label=label,
        title="风险报告",
        state=CraftLoopOutputState.STAGED,
    )


def _grant(
    action: str,
    policy_version: int,
    *,
    label: str | None = None,
    revoked: bool = False,
) -> CraftLoopGrant:
    return CraftLoopGrant(
        loop_id=UUID(int=2),
        ship_action=action,
        label=label,
        actor_user_id=USER,
        policy_version=policy_version,
        revoked_at=NOW if revoked else None,
    )


# ── ledger state machine ──────────────────────────────────────────────────


def test_claim_and_ready_happy_path() -> None:
    item = _item()
    token = claim_item(item, now=NOW)
    assert item.status is CraftLoopItemStatus.IN_PROGRESS
    assert item.attempts == 1
    assert item.claim_expires_at == NOW + timedelta(seconds=600)

    staged = mark_ready(
        item,
        claim_token=token,
        outputs=[{"ship_action": "save_artifacts", "title": "报告"}],
    )
    assert item.status is CraftLoopItemStatus.READY
    assert len(staged) == 1
    assert staged[0].state is CraftLoopOutputState.STAGED
    assert staged[0].ship_action == "save_artifacts"


def test_wrong_claim_token_rejected() -> None:
    item = _item()
    claim_item(item, now=NOW)
    with pytest.raises(LedgerTransitionError, match="claim token"):
        mark_ready(item, claim_token="not-the-token", outputs=[])


def test_invalid_transitions_rejected() -> None:
    item = _item(status=CraftLoopItemStatus.SHIPPED)
    with pytest.raises(LedgerTransitionError):
        assert_transition(item.status, CraftLoopItemStatus.QUEUED)


def test_work_failure_retries_then_parks() -> None:
    item = _item()
    for attempt in range(1, 4):
        claim_item(item, now=NOW)
        status = record_work_failure(item, reason=f"boom {attempt}")
        if attempt < 3:
            assert status is CraftLoopItemStatus.QUEUED
            assert item.guidance == f"boom {attempt}"
    assert item.status is CraftLoopItemStatus.FAILED  # parked after 3 attempts


def test_return_to_work_carries_guidance_and_clears_leases() -> None:
    item = _item(status=CraftLoopItemStatus.READY)
    return_to_work(item, guidance="格式不符，重做")
    assert item.status is CraftLoopItemStatus.QUEUED
    assert item.guidance == "格式不符，重做"
    assert item.claim_token is None and item.decision_token is None


def test_expired_claims_requeued_others_untouched() -> None:
    stale = _item(status=CraftLoopItemStatus.IN_PROGRESS)
    stale.claim_token = "t"
    stale.claim_expires_at = NOW - timedelta(seconds=1)
    fresh = _item(status=CraftLoopItemStatus.IN_PROGRESS)
    fresh.claim_token = "t2"
    fresh.claim_expires_at = NOW + timedelta(seconds=600)
    queued = _item(status=CraftLoopItemStatus.QUEUED)

    requeued = release_expired_claims([stale, fresh, queued], now=NOW)
    assert requeued == 1
    assert stale.status is CraftLoopItemStatus.QUEUED
    assert fresh.status is CraftLoopItemStatus.IN_PROGRESS
    assert queued.status is CraftLoopItemStatus.QUEUED


# ── ship gate ─────────────────────────────────────────────────────────────


def test_gate_hold_without_grant() -> None:
    loop = _loop()
    decision = decide_ship(loop, _output(), grants=[])
    assert decision.auto is False
    assert "human review" in decision.reason


def test_gate_auto_by_policy() -> None:
    loop = _loop(ship_actions=[{"action": "save_artifacts", "gate": "auto"}])
    assert ship_gate_for_action(loop, "save_artifacts") is ShipGate.AUTO
    decision = decide_ship(loop, _output(), grants=[])
    assert decision.auto is True


def test_undeclared_action_always_holds() -> None:
    loop = _loop()
    decision = decide_ship(loop, _output(action="send_email"), grants=[])
    assert decision.auto is False
    assert "undeclared" in decision.reason


def test_grant_covering_rules() -> None:
    grant = _grant("save_artifacts", policy_version=1)
    assert grant_covers(grant, action="save_artifacts", label=None, policy_version=1)
    # policy version mismatch: invalidated
    assert not grant_covers(
        grant, action="save_artifacts", label=None, policy_version=2
    )
    # wrong action
    assert not grant_covers(grant, action="notify_im", label=None, policy_version=1)
    # revoked
    revoked = _grant("save_artifacts", policy_version=1, revoked=True)
    assert not grant_covers(
        revoked, action="save_artifacts", label=None, policy_version=1
    )
    # label scoping
    scoped = _grant("notify_im", policy_version=1, label="财务群")
    assert grant_covers(scoped, action="notify_im", label="财务群", policy_version=1)
    assert not grant_covers(
        scoped, action="notify_im", label="管理层群", policy_version=1
    )
    # unlabeled output covered by any grant on the action
    assert grant_covers(scoped, action="notify_im", label=None, policy_version=1)


def test_granted_action_ships_auto() -> None:
    loop = _loop()
    grants = [_grant("save_artifacts", policy_version=1)]
    decision = decide_ship(loop, _output(), grants=grants)
    assert decision.auto is True
    assert "covered by grant" in decision.reason


def test_policy_bump_invalidates_grants() -> None:
    loop = _loop()
    grant = _grant("save_artifacts", policy_version=loop.policy_version)
    bump_policy_version(loop)
    assert loop.policy_version == 2
    decision = decide_ship(loop, _output(), grants=[grant])
    assert decision.auto is False


def test_graduate_binds_policy_version() -> None:
    loop = _loop()
    grant = graduate(loop, action="save_artifacts", actor_user_id=USER)
    assert grant.policy_version == loop.policy_version
    with pytest.raises(LedgerTransitionError, match="undeclared"):
        graduate(loop, action="unknown_action", actor_user_id=USER)


def test_autopilot_flip_and_back() -> None:
    loop = _loop()
    grants = [_grant("save_artifacts", policy_version=1)]
    set_autopilot(loop, enabled=True)
    assert all(e["gate"] == "auto" for e in loop.ship_actions)
    assert loop.policy_version == 2
    # old grants died with the bump
    assert decide_ship(loop, _output(), grants=grants).auto is True  # gate auto now

    set_autopilot(loop, enabled=False)
    assert all(e["gate"] == "hold" for e in loop.ship_actions)
    assert loop.policy_version == 3
    assert decide_ship(loop, _output(), grants=grants).auto is False


# ── governor ──────────────────────────────────────────────────────────────


def test_governor_escalates_and_recovers() -> None:
    loop = _loop()
    assert evaluate_governor(loop, fire_failed=True) is CraftLoopHealth.HEALTHY
    assert evaluate_governor(loop, fire_failed=True) is CraftLoopHealth.FAILING
    assert evaluate_governor(loop, fire_failed=True) is CraftLoopHealth.QUARANTINED
    assert loop.state is CraftLoopState.QUARANTINED
    assert not loop.state.is_runnable()

    # quarantine is sticky — a success does not clear it
    assert evaluate_governor(loop, fire_failed=False) is CraftLoopHealth.QUARANTINED

    # a healthy loop recovers on success
    loop2 = _loop()
    evaluate_governor(loop2, fire_failed=True)
    assert evaluate_governor(loop2, fire_failed=False) is CraftLoopHealth.HEALTHY
    assert loop2.consecutive_failed_fires == 0
