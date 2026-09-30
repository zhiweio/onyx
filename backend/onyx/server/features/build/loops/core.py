"""Craft loop core logic: ledger transitions, ship gate, governor.

Pure decision functions over the ORM rows (no session access) so every
rule is unit-testable; ``onyx.db.craft_loop`` applies them
transactionally.

QM references: ``loops/ship-gate.ts`` (hold/auto, policy-version-bound
grants), ``loops/item-ledger.ts`` (status machine with claim leases),
``loops/governor.ts`` (health escalation on failed fires).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from onyx.db.enums import (
    CraftLoopHealth,
    CraftLoopItemStatus,
    CraftLoopOutputState,
    CraftLoopState,
    ShipGate,
)
from onyx.db.models import CraftLoop, CraftLoopGrant, CraftLoopItem, CraftLoopOutput
from onyx.utils.logger import setup_logger

logger = setup_logger()

CLAIM_LEASE_SECONDS = 600
DECISION_LEASE_SECONDS = 300
DEFAULT_MAX_ITEM_ATTEMPTS = 3
QUARANTINE_CONSECUTIVE_FAILURES = 3
FAILING_CONSECUTIVE_FAILURES = 2


class LedgerTransitionError(Exception):
    """A transition the ledger state machine refuses."""


_ALLOWED_TRANSITIONS: dict[CraftLoopItemStatus, frozenset[CraftLoopItemStatus]] = {
    CraftLoopItemStatus.QUEUED: frozenset(
        {CraftLoopItemStatus.IN_PROGRESS, CraftLoopItemStatus.SKIPPED}
    ),
    CraftLoopItemStatus.IN_PROGRESS: frozenset(
        {CraftLoopItemStatus.READY, CraftLoopItemStatus.QUEUED, CraftLoopItemStatus.FAILED}
    ),
    CraftLoopItemStatus.READY: frozenset(
        {CraftLoopItemStatus.SHIPPED, CraftLoopItemStatus.QUEUED, CraftLoopItemStatus.FAILED}
    ),
    CraftLoopItemStatus.FAILED: frozenset({CraftLoopItemStatus.QUEUED}),
    CraftLoopItemStatus.SHIPPED: frozenset(),
    CraftLoopItemStatus.SKIPPED: frozenset(),
}


def assert_transition(
    current: CraftLoopItemStatus, target: CraftLoopItemStatus
) -> None:
    allowed = _ALLOWED_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise LedgerTransitionError(
            f"ledger transition {current.value} -> {target.value} is not allowed"
        )


def claim_item(
    item: CraftLoopItem, *, now: datetime | None = None
) -> str:
    """queued → in_progress under a fresh claim lease.

    Raises when the item is not queued. A stale in-progress claim is
    cleared by the reaper path (``release_expired_claims``) before a
    re-queue, so claim itself never steals.
    """
    assert_transition(item.status, CraftLoopItemStatus.IN_PROGRESS)
    now = now or datetime.now(timezone.utc)
    token = uuid4().hex
    item.status = CraftLoopItemStatus.IN_PROGRESS
    item.attempts += 1
    item.claim_token = token
    item.claim_expires_at = now + timedelta(seconds=CLAIM_LEASE_SECONDS)
    return token


def verify_claim(item: CraftLoopItem, token: str) -> None:
    if item.claim_token != token:
        raise LedgerTransitionError("claim token mismatch — lease lost or stolen")


def record_work_failure(
    item: CraftLoopItem,
    *,
    reason: str,
    max_attempts: int = DEFAULT_MAX_ITEM_ATTEMPTS,
) -> CraftLoopItemStatus:
    """in_progress → queued (retry with guidance) or failed (parked)."""
    if item.attempts >= max_attempts:
        item.status = CraftLoopItemStatus.FAILED
        item.guidance = f"attempt {item.attempts} failed: {reason}"
        item.claim_token = None
        item.claim_expires_at = None
        return item.status
    return return_to_work(item, guidance=reason)


def return_to_work(item: CraftLoopItem, *, guidance: str) -> CraftLoopItemStatus:
    """ready/in_progress → queued with a reviewer note for the next attempt."""
    assert_transition(item.status, CraftLoopItemStatus.QUEUED)
    item.status = CraftLoopItemStatus.QUEUED
    item.guidance = guidance
    item.claim_token = None
    item.claim_expires_at = None
    item.decision_token = None
    item.decision_expires_at = None
    return item.status


def release_expired_claims(
    items: list[CraftLoopItem], *, now: datetime | None = None
) -> int:
    """Requeue in-progress items whose claim lease has lapsed.

    Returns the number requeued. Worker-crash recovery: the reaper call
    before every fire makes abandoned claims re-workable.
    """
    now = now or datetime.now(timezone.utc)
    requeued = 0
    for item in items:
        if item.status is not CraftLoopItemStatus.IN_PROGRESS:
            continue
        expires = item.claim_expires_at
        if expires is not None and expires > now:
            continue
        item.status = CraftLoopItemStatus.QUEUED
        item.claim_token = None
        item.claim_expires_at = None
        requeued += 1
    return requeued


def mark_ready(
    item: CraftLoopItem, *, claim_token: str, outputs: list[dict[str, Any]]
) -> list[CraftLoopOutput]:
    """in_progress → ready with staged outputs (kept as dicts by callers;
    this pure helper returns the rows to attach)."""
    verify_claim(item, claim_token)
    assert_transition(item.status, CraftLoopItemStatus.READY)
    item.status = CraftLoopItemStatus.READY
    item.claim_token = None
    item.claim_expires_at = None
    staged: list[CraftLoopOutput] = []
    for output in outputs:
        staged.append(
            CraftLoopOutput(
                loop_id=item.loop_id,
                item_id=item.id,
                ship_action=str(output.get("ship_action") or "save_artifacts"),
                label=output.get("label"),
                title=str(output.get("title") or ""),
                summary=str(output.get("summary") or ""),
                state=CraftLoopOutputState.STAGED,
            )
        )
    return staged


# ── ship gate ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ShipDecision:
    auto: bool
    reason: str


def grant_covers(
    grant: CraftLoopGrant, *, action: str, label: str | None, policy_version: int
) -> bool:
    """A grant applies only at the policy version it was issued for, for
    its action and (when label-scoped) its label. Revoked never covers."""
    if grant.revoked_at is not None:
        return False
    if grant.policy_version != policy_version:
        return False
    if grant.ship_action != action:
        return False
    if grant.label is not None and label is not None and grant.label != label:
        return False
    return True


def ship_gate_for_action(loop: CraftLoop, action: str) -> ShipGate | None:
    for entry in loop.ship_actions or []:
        if entry.get("action") == action:
            raw = str(entry.get("gate") or ShipGate.HOLD.value).lower()
            return ShipGate.AUTO if raw == ShipGate.AUTO.value else ShipGate.HOLD
    return None


def decide_ship(
    loop: CraftLoop,
    output: CraftLoopOutput,
    grants: list[CraftLoopGrant],
) -> ShipDecision:
    """QM ``decideShip``: undeclared action → hold; gate auto → auto;
    covering grant → auto; otherwise hold for human review."""
    gate = ship_gate_for_action(loop, output.ship_action)
    if gate is None:
        return ShipDecision(
            auto=False, reason=f"undeclared ship action {output.ship_action!r}"
        )
    if gate is ShipGate.AUTO:
        return ShipDecision(auto=True, reason="gate is auto by policy")
    for grant in grants:
        if grant_covers(
            grant,
            action=output.ship_action,
            label=output.label,
            policy_version=loop.policy_version,
        ):
            return ShipDecision(
                auto=True,
                reason=f"covered by grant {grant.id} (policy v{grant.policy_version})",
            )
    return ShipDecision(auto=False, reason="no grant — human review required")


def graduate(
    loop: CraftLoop,
    *,
    action: str,
    actor_user_id: UUID,
    label: str | None = None,
) -> CraftLoopGrant:
    """Issue a standing grant at the loop's current policy version."""
    if ship_gate_for_action(loop, action) is None:
        raise LedgerTransitionError(
            f"cannot graduate undeclared ship action {action!r}"
        )
    return CraftLoopGrant(
        loop_id=loop.id,
        ship_action=action,
        label=label,
        actor_user_id=actor_user_id,
        policy_version=loop.policy_version,
    )


def bump_policy_version(loop: CraftLoop) -> None:
    """Invalidate every standing grant (playbook or ship-action edit)."""
    loop.policy_version += 1


def set_autopilot(
    loop: CraftLoop,
    *,
    enabled: bool,
) -> None:
    """Flip every declared gate. On: all auto. Off: all hold + a policy
    bump, which also revokes-by-invalidation any standing grants."""
    new_gate = ShipGate.AUTO if enabled else ShipGate.HOLD
    loop.ship_actions = [
        {**entry, "gate": new_gate.value} for entry in (loop.ship_actions or [])
    ]
    bump_policy_version(loop)


# ── governor ──────────────────────────────────────────────────────────────


def evaluate_governor(
    loop: CraftLoop,
    *,
    fire_failed: bool,
) -> CraftLoopHealth:
    """Health after one fire outcome.

    quarantine: undeclared ship action surfaced, or 3+ consecutive failed
    fires — the loop stops being runnable until a human intervenes.
    failing: 2 consecutive failed fires.
    Recovery: one successful fire clears the streak; quarantine only
    clears manually.
    """
    if loop.health is CraftLoopHealth.QUARANTINED:
        return CraftLoopHealth.QUARANTINED
    if fire_failed:
        loop.consecutive_failed_fires += 1
    else:
        loop.consecutive_failed_fires = 0
    if loop.consecutive_failed_fires >= QUARANTINE_CONSECUTIVE_FAILURES:
        loop.health = CraftLoopHealth.QUARANTINED
        loop.state = CraftLoopState.QUARANTINED
    elif loop.consecutive_failed_fires >= FAILING_CONSECUTIVE_FAILURES:
        loop.health = CraftLoopHealth.FAILING
    else:
        loop.health = CraftLoopHealth.HEALTHY
    return loop.health
