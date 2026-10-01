"""Craft loop DAL: due-loop claiming, CRUD, item/output/grant helpers.

The claiming discipline mirrors ``onyx.db.scheduled_task``: the caller
must, in the same transaction as ``claim_due_loops``, enqueue its work
and call ``advance_next_fire_at`` before committing — releasing the row
locks without advancing would let a concurrent tick double-fire.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from onyx.db.enums import (
    CraftLoopHealth,
    CraftLoopItemStatus,
    CraftLoopState,
    ShipGate,
)
from onyx.db.models import (
    CraftLoop,
    CraftLoopGrant,
    CraftLoopItem,
    CraftLoopOutput,
    User,
)
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.server.features.build.scheduled_tasks.schedule import compute_next_run_at
from onyx.utils.logger import setup_logger

logger = setup_logger()

MAX_ITEMS_PER_FIRE_DEFAULT = 5


# ── loop CRUD ─────────────────────────────────────────────────────────────


def get_craft_loop(
    db_session: Session, loop_id: UUID, *, for_update: bool = False
) -> CraftLoop | None:
    stmt = select(CraftLoop).where(CraftLoop.id == loop_id)
    if for_update:
        stmt = stmt.with_for_update()
    return db_session.scalar(stmt)


def get_craft_loop_or_404(
    db_session: Session, loop_id: UUID, *, for_update: bool = False
) -> CraftLoop:
    loop = get_craft_loop(db_session, loop_id, for_update=for_update)
    if loop is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, f"Craft loop {loop_id} not found")
    return loop


def list_craft_loops_for_user(db_session: Session, user_id: UUID) -> list[CraftLoop]:
    return list(
        db_session.scalars(
            select(CraftLoop)
            .where(CraftLoop.user_id == user_id)
            .order_by(CraftLoop.created_at.desc())
        )
    )


def create_craft_loop(
    db_session: Session,
    *,
    user_id: UUID,
    name: str,
    playbook: dict | None = None,
    ship_actions: list[dict] | None = None,
    success_condition: str = "",
    trigger_cron: str | None = None,
    scenario_id: UUID | None = None,
    caps: dict | None = None,
) -> CraftLoop:
    loop = CraftLoop(
        user_id=user_id,
        name=name.strip() or "未命名循环",
        playbook=playbook or {},
        ship_actions=_validated_ship_actions(ship_actions),
        success_condition=success_condition,
        trigger_cron=trigger_cron,
        scenario_id=scenario_id,
        caps=caps or {},
        state=CraftLoopState.ENABLED,
        health=CraftLoopHealth.HEALTHY,
    )
    if trigger_cron:
        loop.next_fire_at = compute_next_run_at(
            trigger_cron, datetime.now(timezone.utc)
        )
    db_session.add(loop)
    db_session.flush()
    return loop


def update_craft_loop(
    db_session: Session,
    loop_id: UUID,
    *,
    name: str | None = None,
    playbook: dict | None = None,
    ship_actions: list[dict] | None = None,
    success_condition: str | None = None,
    trigger_cron: str | None = None,
    state: CraftLoopState | None = None,
) -> CraftLoop:
    from onyx.server.features.build.loops.core import bump_policy_version

    loop = get_craft_loop_or_404(db_session, loop_id, for_update=True)
    if name is not None and name.strip():
        loop.name = name.strip()
    policy_changed = False
    if playbook is not None:
        loop.playbook = playbook
        policy_changed = True
    if ship_actions is not None:
        loop.ship_actions = _validated_ship_actions(ship_actions)
        policy_changed = True
    if success_condition is not None:
        loop.success_condition = success_condition
    if trigger_cron is not None:
        loop.trigger_cron = trigger_cron
        loop.next_fire_at = (
            compute_next_run_at(trigger_cron, datetime.now(timezone.utc))
            if trigger_cron and loop.state.is_runnable()
            else None
        )
    if state is not None:
        loop.state = state
        if state.is_runnable() and loop.trigger_cron and loop.next_fire_at is None:
            loop.next_fire_at = compute_next_run_at(
                loop.trigger_cron, datetime.now(timezone.utc)
            )
        elif not state.is_runnable():
            loop.next_fire_at = None
    if policy_changed:
        bump_policy_version(loop)
    db_session.flush()
    return loop


def delete_craft_loop(db_session: Session, loop_id: UUID) -> None:
    loop = get_craft_loop_or_404(db_session, loop_id)
    db_session.delete(loop)
    db_session.flush()


def _validated_ship_actions(entries: list[dict] | None) -> list[dict]:
    actions: list[dict] = []
    seen: set[str] = set()
    for entry in entries or []:
        action = str(entry.get("action") or "").strip()
        if not action or action in seen:
            continue
        seen.add(action)
        gate = str(entry.get("gate") or ShipGate.HOLD.value).lower()
        actions.append(
            {
                "action": action,
                "gate": ShipGate.AUTO.value
                if gate == ShipGate.AUTO.value
                else ShipGate.HOLD.value,
            }
        )
    return actions


# ── sweep claiming ────────────────────────────────────────────────────────


def claim_due_loops(
    db_session: Session, *, now: datetime, batch_size: int
) -> list[CraftLoop]:
    """Atomically claim due, runnable loops (FOR UPDATE SKIP LOCKED)."""
    if batch_size <= 0:
        return []
    stmt = (
        select(CraftLoop)
        .options(selectinload(CraftLoop.user))
        .where(
            CraftLoop.state == CraftLoopState.ENABLED,
            CraftLoop.health != CraftLoopHealth.QUARANTINED,
            CraftLoop.next_fire_at.is_not(None),
            CraftLoop.next_fire_at <= now,
        )
        .order_by(CraftLoop.next_fire_at)
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    )
    return list(db_session.execute(stmt).scalars())


def advance_next_fire_at(
    db_session: Session, *, loop: CraftLoop, now: datetime
) -> datetime | None:
    """Recompute ``next_fire_at`` from ``now``; None without a cron."""
    if not loop.trigger_cron:
        loop.next_fire_at = None
        db_session.flush()
        return None
    loop.next_fire_at = compute_next_run_at(loop.trigger_cron, now)
    db_session.flush()
    return loop.next_fire_at


# ── items ─────────────────────────────────────────────────────────────────


def get_loop_item(db_session: Session, item_id: UUID) -> CraftLoopItem | None:
    return db_session.scalar(select(CraftLoopItem).where(CraftLoopItem.id == item_id))


def get_loop_item_or_404(db_session: Session, item_id: UUID) -> CraftLoopItem:
    item = get_loop_item(db_session, item_id)
    if item is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, f"Loop item {item_id} not found")
    return item


def list_loop_items(
    db_session: Session,
    loop_id: UUID,
    *,
    statuses: Sequence[CraftLoopItemStatus] | None = None,
    limit: int | None = None,
) -> list[CraftLoopItem]:
    stmt = select(CraftLoopItem).where(CraftLoopItem.loop_id == loop_id)
    if statuses:
        stmt = stmt.where(CraftLoopItem.status.in_(list(statuses)))
    stmt = stmt.order_by(CraftLoopItem.created_at)
    if limit:
        stmt = stmt.limit(limit)
    return list(db_session.scalars(stmt))


def enqueue_loop_items(
    db_session: Session,
    loop_id: UUID,
    items: list[dict],
) -> list[CraftLoopItem]:
    """Upsert by source_key: new facts queue; known ones refresh summaries."""
    created: list[CraftLoopItem] = []
    existing = {item.source_key: item for item in list_loop_items(db_session, loop_id)}
    for entry in items:
        source_key = str(entry.get("source_key") or "").strip()
        if not source_key:
            continue
        summary = str(entry.get("summary") or "")
        if source_key in existing:
            row = existing[source_key]
            if row.status.is_terminal():
                continue
            row.source_summary = summary or row.source_summary
            continue
        row = CraftLoopItem(
            loop_id=loop_id,
            source_key=source_key[:512],
            source_summary=summary,
            status=CraftLoopItemStatus.QUEUED,
        )
        db_session.add(row)
        created.append(row)
    db_session.flush()
    return created


# ── outputs + grants ──────────────────────────────────────────────────────


def get_loop_output(db_session: Session, output_id: UUID) -> CraftLoopOutput | None:
    return db_session.scalar(
        select(CraftLoopOutput).where(CraftLoopOutput.id == output_id)
    )


def active_grants_for_loop(db_session: Session, loop_id: UUID) -> list[CraftLoopGrant]:
    return list(
        db_session.scalars(
            select(CraftLoopGrant).where(
                CraftLoopGrant.loop_id == loop_id,
                CraftLoopGrant.revoked_at.is_(None),
            )
        )
    )


def loop_owner(db_session: Session, loop: CraftLoop) -> User:
    # fastapi-users declares User.id as a plain UUID under TYPE_CHECKING; at
    # runtime it is a mapped column.
    owner = db_session.scalar(
        select(User).where(User.id == loop.user_id)  # ty: ignore[invalid-argument-type]
    )
    assert owner is not None
    return owner
