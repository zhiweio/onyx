"""Craft loop REST API: CRUD, ledger intake, ship decisions, graduation.

Mirrors the scheduled-task API surface conventions (owner-scoped rows,
approval-style decision bodies) on top of ``db.craft_loop`` and the
``loops.core`` decision rules.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from onyx.auth.permissions import require_permission
from onyx.db.craft_loop import (
    active_grants_for_loop,
    create_craft_loop,
    delete_craft_loop,
    enqueue_loop_items,
    get_craft_loop_or_404,
    get_loop_item_or_404,
    get_loop_output,
    list_craft_loops_for_user,
    list_loop_items,
    update_craft_loop,
)
from onyx.db.engine.sql_engine import get_session
from onyx.db.enums import (
    CraftLoopItemStatus,
    CraftLoopOutputState,
    CraftLoopState,
    Permission,
)
from onyx.db.models import CraftLoopGrant, User
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.server.features.build.loops.core import (
    graduate,
    set_autopilot,
)
from onyx.utils.logger import setup_logger

logger = setup_logger()

router = APIRouter(prefix="/loops")


# ── request/response models ───────────────────────────────────────────────


class ShipActionSpec(BaseModel):
    action: str
    gate: str = "hold"  # hold | auto


class LoopCreateRequest(BaseModel):
    name: str
    description: str = ""
    playbook: dict[str, Any] = Field(default_factory=dict)
    ship_actions: list[ShipActionSpec] = Field(default_factory=list)
    success_condition: str = ""
    trigger_cron: str | None = None
    scenario_id: UUID | None = None
    caps: dict[str, Any] = Field(default_factory=dict)


class LoopUpdateRequest(BaseModel):
    name: str | None = None
    playbook: dict[str, Any] | None = None
    ship_actions: list[ShipActionSpec] | None = None
    success_condition: str | None = None
    trigger_cron: str | None = None
    state: str | None = None  # enabled | paused | archived


class LoopItemIntakeRequest(BaseModel):
    items: list[dict[str, Any]]


class OutputDecisionRequest(BaseModel):
    decision: str  # ship | return
    note: str | None = None


class GrantRequest(BaseModel):
    ship_action: str
    label: str | None = None


class AutopilotRequest(BaseModel):
    enabled: bool


# ── serialization ─────────────────────────────────────────────────────────


def _serialize_loop(loop: Any, *, _with_ledger: bool = True) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": str(loop.id),
        "name": loop.name,
        "description": loop.description,
        "playbook": loop.playbook,
        "ship_actions": loop.ship_actions,
        "success_condition": loop.success_condition,
        "caps": loop.caps,
        "state": loop.state.value,
        "health": loop.health.value,
        "policy_version": loop.policy_version,
        "consecutive_failed_fires": loop.consecutive_failed_fires,
        "trigger_cron": loop.trigger_cron,
        "next_fire_at": loop.next_fire_at.isoformat() if loop.next_fire_at else None,
        "scenario_id": str(loop.scenario_id) if loop.scenario_id else None,
        "created_at": loop.created_at.isoformat(),
    }
    return data


def _serialize_item(item: Any) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "source_key": item.source_key,
        "source_summary": item.source_summary,
        "status": item.status.value,
        "attempts": item.attempts,
        "guidance": item.guidance,
        "created_at": item.created_at.isoformat(),
    }


def _serialize_output(output: Any) -> dict[str, Any]:
    return {
        "id": str(output.id),
        "item_id": str(output.item_id),
        "ship_action": output.ship_action,
        "label": output.label,
        "title": output.title,
        "summary": output.summary,
        "state": output.state.value,
        "decided_by": str(output.decided_by) if output.decided_by else None,
        "decided_at": output.decided_at.isoformat() if output.decided_at else None,
    }


def _serialize_grant(grant: CraftLoopGrant) -> dict[str, Any]:
    return {
        "id": str(grant.id),
        "ship_action": grant.ship_action,
        "label": grant.label,
        "policy_version": grant.policy_version,
        "created_at": grant.created_at.isoformat(),
        "revoked_at": grant.revoked_at.isoformat() if grant.revoked_at else None,
    }


# ── loop CRUD ─────────────────────────────────────────────────────────────


@router.get("")
def list_loops(
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    loops = list_craft_loops_for_user(db_session, user.id)
    return [_loop_payload(db_session, loop) for loop in loops]


def _loop_payload(db_session: Session, loop: Any) -> dict[str, Any]:
    data = _serialize_loop(loop)
    ledger = list_loop_items(db_session, loop.id)
    data["counts"] = {
        status.value: sum(1 for i in ledger if i.status is status)
        for status in CraftLoopItemStatus
    }
    return data


@router.get("/{loop_id}")
def get_loop(
    loop_id: UUID,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> dict[str, Any]:
    _require_owner(db_session, loop_id, user)
    return _loop_payload(db_session, get_craft_loop_or_404(db_session, loop_id))


@router.post("")
def create_loop(
    request: LoopCreateRequest,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> dict[str, Any]:
    loop = create_craft_loop(
        db_session,
        user_id=user.id,
        name=request.name,
        playbook=request.playbook,
        ship_actions=[entry.model_dump() for entry in request.ship_actions],
        success_condition=request.success_condition,
        trigger_cron=request.trigger_cron,
        scenario_id=request.scenario_id,
        caps=request.caps,
    )
    db_session.commit()
    return _serialize_loop(loop)


@router.patch("/{loop_id}")
def update_loop(
    loop_id: UUID,
    request: LoopUpdateRequest,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> dict[str, Any]:
    _require_owner(db_session, loop_id, user)
    loop = update_craft_loop(
        db_session,
        loop_id,
        name=request.name,
        playbook=request.playbook,
        ship_actions=(
            [entry.model_dump() for entry in request.ship_actions]
            if request.ship_actions is not None
            else None
        ),
        success_condition=request.success_condition,
        trigger_cron=request.trigger_cron,
        state=CraftLoopState(request.state) if request.state else None,
    )
    db_session.commit()
    return _serialize_loop(loop)


@router.delete("/{loop_id}")
def delete_loop(
    loop_id: UUID,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> dict[str, Any]:
    _require_owner(db_session, loop_id, user)
    delete_craft_loop(db_session, loop_id)
    db_session.commit()
    return {"success": True}


# ── ledger intake ─────────────────────────────────────────────────────────


@router.post("/{loop_id}/items")
def intake_items(
    loop_id: UUID,
    request: LoopItemIntakeRequest,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> dict[str, Any]:
    _require_owner(db_session, loop_id, user)
    created = enqueue_loop_items(db_session, loop_id, request.items)
    db_session.commit()
    return {"created": len(created), "items": [_serialize_item(i) for i in created]}


@router.get("/{loop_id}/items")
def list_items(
    loop_id: UUID,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    _require_owner(db_session, loop_id, user)
    return [_serialize_item(i) for i in list_loop_items(db_session, loop_id)]


@router.post("/{loop_id}/items/{item_id}/retry")
def retry_item(
    loop_id: UUID,
    item_id: UUID,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> dict[str, Any]:
    _require_owner(db_session, loop_id, user)
    item = get_loop_item_or_404(db_session, item_id)
    if item.loop_id != loop_id:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "item does not belong to loop")
    if item.status not in (CraftLoopItemStatus.FAILED,):
        raise OnyxError(
            OnyxErrorCode.CONFLICT, f"cannot retry item in status {item.status.value}"
        )
    item.status = CraftLoopItemStatus.QUEUED
    item.guidance = None
    db_session.commit()
    return _serialize_item(item)


# ── outputs + ship decisions ──────────────────────────────────────────────


@router.get("/{loop_id}/outputs")
def list_outputs(
    loop_id: UUID,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    _require_owner(db_session, loop_id, user)
    items = list_loop_items(db_session, loop_id)
    outputs: list[dict[str, Any]] = []
    outputs.extend(
        _serialize_output(output) for item in items for output in item.outputs
    )
    return outputs


@router.post("/{loop_id}/outputs/{output_id}/decision")
def decide_output(
    loop_id: UUID,
    output_id: UUID,
    request: OutputDecisionRequest,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Human ship decision on a held output: ship or return to work."""
    _require_owner(db_session, loop_id, user)
    output = get_loop_output(db_session, output_id)
    if output is None or output.loop_id != loop_id:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "output not found")
    if output.state is not CraftLoopOutputState.READY:
        raise OnyxError(
            OnyxErrorCode.CONFLICT,
            f"output in state {output.state.value} is not awaiting a decision",
        )
    now = datetime.now(timezone.utc)
    if request.decision == "ship":
        output.state = CraftLoopOutputState.SHIPPED
        output.decided_by = user.id
        output.decided_at = now
        # A human ship on an un-granted action issues a per-label-free
        # standing grant at the current policy version (graduation).
        loop = get_craft_loop_or_404(db_session, loop_id)
        grant = graduate(
            loop, action=output.ship_action, actor_user_id=user.id, label=output.label
        )
        db_session.add(grant)
    elif request.decision == "return":
        output.state = CraftLoopOutputState.RETURNED
        output.decided_by = user.id
        output.decided_at = now
        item = output.item
        from onyx.server.features.build.loops.core import return_to_work

        return_to_work(item, guidance=request.note or "人工退回重做")
    else:
        raise OnyxError(
            OnyxErrorCode.VALIDATION_ERROR, "decision must be 'ship' or 'return'"
        )
    db_session.commit()
    return _serialize_output(output)


# ── graduation controls ───────────────────────────────────────────────────


@router.get("/{loop_id}/grants")
def list_grants(
    loop_id: UUID,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    _require_owner(db_session, loop_id, user)
    grants = (
        db_session.query(CraftLoopGrant)
        .filter(CraftLoopGrant.loop_id == loop_id)
        .order_by(CraftLoopGrant.created_at.desc())
        .all()
    )
    return [_serialize_grant(grant) for grant in grants]


@router.post("/{loop_id}/grants")
def grant_loop_action(
    loop_id: UUID,
    request: GrantRequest,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> dict[str, Any]:
    _require_owner(db_session, loop_id, user)
    loop = get_craft_loop_or_404(db_session, loop_id)
    grant = graduate(
        loop,
        action=request.ship_action,
        actor_user_id=user.id,
        label=request.label,
    )
    db_session.add(grant)
    db_session.commit()
    return _serialize_grant(grant)


@router.post("/{loop_id}/autopilot")
def set_loop_autopilot(
    loop_id: UUID,
    request: AutopilotRequest,
    user: User = Depends(require_permission(Permission.BASIC_ACCESS)),
    db_session: Session = Depends(get_session),
) -> dict[str, Any]:
    _require_owner(db_session, loop_id, user)
    loop = get_craft_loop_or_404(db_session, loop_id, for_update=True)
    set_autopilot(loop, enabled=request.enabled)
    # revoking standing grants explicitly on disable (belt to the
    # policy-version suspenders)
    if not request.enabled:
        for grant in active_grants_for_loop(db_session, loop.id):
            grant.revoked_at = datetime.now(timezone.utc)
    db_session.commit()
    return _serialize_loop(loop)


# ── helpers ───────────────────────────────────────────────────────────────


def _require_owner(db_session: Session, loop_id: UUID, user: User) -> None:
    loop = get_craft_loop_or_404(db_session, loop_id)
    if loop.user_id != user.id:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, f"Craft loop {loop_id} not found")
