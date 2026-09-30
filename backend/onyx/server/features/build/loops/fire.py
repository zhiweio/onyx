"""Craft loop fire machinery: the sweep and the per-item executor.

The sweep (beat-driven, 30s) claims due loops, reclaims expired item
leases, claims queued items up to the loop's per-fire cap, advances the
loop's next_fire_at and — after commit — dispatches one celery task per
claimed item, mirroring ``dispatch_due_scheduled_tasks``.

``run_loop_item_logic`` mirrors the scheduled-task executor's
``_drive_agent``: a fresh BuildSession per item, the same event loop
(masking, prompt-slot lease, turn deadline, budget, approval parking),
then ledger finalization — stage outputs from the sandbox, run the ship
gate per output (auto ships, hold parks with a notification), and feed
the governor.

Item intake this round is API-driven (POST /build/loops/{id}/items);
agent-driven intake turns are a follow-up on the same executor.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from onyx.configs.constants import MessageType, NotificationType
from onyx.db.craft_loop import (
    MAX_ITEMS_PER_FIRE_DEFAULT,
    advance_next_fire_at,
    claim_due_loops,
    get_craft_loop_or_404,
    get_loop_item,
    list_loop_items,
)
from onyx.db.engine.sql_engine import get_session_with_current_tenant
from onyx.db.enums import (
    CraftLoopItemStatus,
    CraftLoopOutputState,
    SessionOrigin,
)
from onyx.db.models import Sandbox
from onyx.db.notification import create_notification
from onyx.server.features.build.db.build_session import create_message
from onyx.server.features.build.db.sandbox import update_sandbox_heartbeat
from onyx.server.features.build.env_vars.masking import (
    SecretMasker,
    mask_sandbox_event,
)
from onyx.server.features.build.loops.core import (
    claim_item,
    decide_ship,
    evaluate_governor,
    mark_ready,
    record_work_failure,
    release_expired_claims,
    verify_claim,
)
from onyx.server.features.build.sandbox.event_schema import (
    TURN_ERROR_CODE_TIMEOUT,
    Error,
    PromptResponse,
    RequestPermissionRequest,
)
from onyx.server.features.build.session.locks import session_creation_lock
from onyx.server.features.build.session.manager import SessionManager
from onyx.server.features.build.session.streaming import BuildStreamingState
from onyx.server.features.build.timeouts import (
    PROVISION_WAIT_SECONDS,
    SCHEDULED_RUN_HARD_CAP_SECONDS,
    SCHEDULED_RUN_SOFT_BUDGET_SECONDS,
)
from onyx.utils.logger import setup_logger

logger = setup_logger()

_EMPTY_MASKER = SecretMasker([])
SWEEP_BATCH_SIZE = 20


class _Outcome:
    __slots__ = ("ok", "held", "detail")

    def __init__(self, ok: bool, held: bool = False, detail: str = "") -> None:
        self.ok = ok
        self.held = held
        self.detail = detail


def loops_fire_sweep_logic(*, tenant_id: str | None = None) -> list[dict[str, Any]]:
    """One sweep tick: claim due loops, lease queued items, dispatch work.

    Returns a dispatch manifest (loop_id, item_id, claim_token) mainly
    for tests; production callers forward each entry to the item task.
    """
    del tenant_id  # caller contextvar carries the tenant in celery tasks
    now = datetime.now(timezone.utc)
    manifest: list[dict[str, Any]] = []
    with get_session_with_current_tenant() as db_session:
        loops = claim_due_loops(db_session, now=now, batch_size=SWEEP_BATCH_SIZE)
        for loop in loops:
            items = list_loop_items(db_session, loop.id)
            release_expired_claims(items, now=now)  # crash recovery
            cap = int(
                (loop.caps or {}).get("max_items_per_fire") or MAX_ITEMS_PER_FIRE_DEFAULT
            )
            claimed = 0
            for item in items:
                if claimed >= cap:
                    break
                if item.status is not CraftLoopItemStatus.QUEUED:
                    continue
                token = claim_item(item, now=now)
                manifest.append(
                    {
                        "loop_id": str(loop.id),
                        "item_id": str(item.id),
                        "claim_token": token,
                        "user_id": str(loop.user_id),
                    }
                )
                claimed += 1
            advance_next_fire_at(db_session, loop=loop, now=now)
        db_session.commit()
    return manifest


def run_loop_item_logic(
    item_id: UUID,
    *,
    claim_token: str,
    budget_seconds: int = SCHEDULED_RUN_HARD_CAP_SECONDS,
) -> None:
    """Execute one claimed ledger item end-to-end; never raises.

    Idempotency: the claim token must still match — a re-claimed item
    (lease expired, another worker took it) exits silently.
    """
    try:
        _execute_item(item_id, claim_token, budget_seconds)
    except Exception:
        logger.exception("Loop item %s executor crashed", item_id)
        _safe_fail(item_id, claim_token, "executor crash")


def _execute_item(item_id: UUID, claim_token: str, budget_seconds: int) -> None:
    with get_session_with_current_tenant() as db_session:
        item = get_loop_item(db_session, item_id)
        if item is None:
            logger.warning("Loop item %s vanished; nothing to do", item_id)
            return
        try:
            verify_claim(item, claim_token)
        except Exception:
            logger.info("Loop item %s claim token stale; skipping", item_id)
            return
        loop = get_craft_loop_or_404(db_session, item.loop_id, for_update=True)
        owner_id = loop.user_id
        loop_name = loop.name
        prompt = _build_item_prompt(loop, item)

        session_manager = SessionManager(db_session)
        sandbox = session_manager.ensure_sandbox_running(
            owner_id, provisioning_wait_seconds=PROVISION_WAIT_SECONDS
        )
        sandbox_id = sandbox.id

        with session_creation_lock(owner_id):
            build_session = session_manager.create_session(
                user_id=owner_id,
                origin=SessionOrigin.SCHEDULED,
                name=f"Loop: {loop_name}",
            )
            session_id = build_session.id
            create_message(
                session_id=session_id,
                message_type=MessageType.USER,
                turn_index=0,
                message_metadata={
                    "type": "user_message",
                    "content": {"type": "text", "text": prompt},
                },
                db_session=db_session,
            )
            update_sandbox_heartbeat(db_session, sandbox_id)
            db_session.commit()

        outcome = _drive_item_turn(
            session_manager=session_manager,
            db_session=db_session,
            sandbox_id=sandbox_id,
            session_id=session_id,
            prompt=prompt,
            budget_seconds=budget_seconds,
        )

        if outcome.held:
            # Mid-turn tool approval parked the turn; the item returns to
            # the queue when the approval resolves (or the lease expires)
            # so the work re-runs with the approval granted.
            from onyx.server.features.build.loops.core import return_to_work

            return_to_work(item, guidance="turn parked on a tool approval")
            evaluate_governor(loop, fire_failed=False)
            db_session.commit()
            return

        if not outcome.ok:
            record_work_failure(
                item,
                reason=outcome.detail or "agent turn failed",
                max_attempts=_max_attempts(loop),
            )
            evaluate_governor(loop, fire_failed=True)
            _notify(
                db_session,
                user_id=owner_id,
                notif_type=NotificationType.LOOP_ITEM_FAILED,
                title=f'循环 "{loop_name}" 的条目失败',
                description=outcome.detail,
            )
            db_session.commit()
            return

        # Success: stage declared outputs from the sandbox.
        outputs = _collect_outputs(session_manager, session_id, sandbox_id, owner_id, loop)
        if outputs:
            staged = mark_ready(item, claim_token=claim_token, outputs=outputs)
            for row in staged:
                db_session.add(row)
                db_session.flush()
        else:
            # No declared outputs: treat as a failed contract — retry with
            # guidance so the agent declares outputs next attempt.
            record_work_failure(
                item,
                reason="agent produced no declared outputs",
                max_attempts=_max_attempts(loop),
            )
            evaluate_governor(loop, fire_failed=True)
            db_session.commit()
            return

        # Ship gate per staged output.
        from onyx.db.craft_loop import active_grants_for_loop

        grants = active_grants_for_loop(db_session, loop.id)
        for row in staged:
            decision = decide_ship(loop, row, grants)
            if decision.auto:
                row.state = CraftLoopOutputState.SHIPPED
            else:
                row.state = CraftLoopOutputState.READY  # held for human
                _notify(
                    db_session,
                    user_id=owner_id,
                    notif_type=NotificationType.LOOP_OUTPUT_HELD,
                    title=f'循环 "{loop_name}" 有产出待审核',
                    description=row.title or row.ship_action,
                    additional_data={"loop_id": str(loop.id), "output_id": str(row.id)},
                )
        evaluate_governor(loop, fire_failed=False)
        db_session.commit()
        logger.info("Loop item %s completed (held=%d)", item_id, sum(1 for r in staged if r.state is CraftLoopOutputState.READY))


def _drive_item_turn(
    *,
    session_manager: SessionManager,
    db_session: Any,
    sandbox_id: UUID,
    session_id: UUID,
    prompt: str,
    budget_seconds: int,
) -> _Outcome:
    """The event loop, condensed from the scheduled-task executor."""
    state = BuildStreamingState(turn_index=0)
    deadline = time.monotonic() + budget_seconds
    prompt_slot_cm = session_manager.prompt_slot(sandbox_id, session_id)
    slot = prompt_slot_cm.__enter__()
    if not slot.acquired:
        prompt_slot_cm.__exit__(None, None, None)
        return _Outcome(ok=False, detail="concurrent turn in flight")
    try:
        session_manager.stamp_turn_deadline(
            sandbox_id,
            session_id,
            soft_budget_seconds=min(SCHEDULED_RUN_SOFT_BUDGET_SECONDS, budget_seconds),
            hard_cap_seconds=budget_seconds,
        )
        terminal_error: Error | None = None
        got_response = False
        for sandbox_event in session_manager.yield_sandbox_events(
            sandbox_id,
            session_id,
            prompt,
            turn_timeout_seconds=float(budget_seconds),
        ):
            sandbox_event = mask_sandbox_event(sandbox_event, _EMPTY_MASKER)
            slot.extend()
            if slot.lost:
                session_manager.finalize_persist(session_id, state)
                db_session.commit()
                return _Outcome(ok=False, detail="prompt slot lease lost")
            if isinstance(sandbox_event, RequestPermissionRequest):
                session_manager.finalize_persist(session_id, state)
                db_session.commit()
                return _Outcome(ok=False, held=True, detail="approval gate")
            if isinstance(sandbox_event, Error):
                terminal_error = sandbox_event
                break
            if isinstance(sandbox_event, PromptResponse):
                if getattr(sandbox_event, "stop_reason", None) == "cancelled":
                    return _Outcome(ok=False, detail="agent turn aborted")
                got_response = True
                break
            if time.monotonic() > deadline:
                session_manager.finalize_persist(session_id, state)
                db_session.commit()
                return _Outcome(ok=False, detail=f"budget exceeded ({budget_seconds}s)")
            session_manager.persist_sandbox_event(session_id, state, sandbox_event)
            db_session.commit()

        session_manager.finalize_persist(session_id, state)
        db_session.commit()
        if terminal_error is not None:
            detail = terminal_error.message or "agent turn error"
            if terminal_error.code == TURN_ERROR_CODE_TIMEOUT:
                detail = f"turn timeout: {detail}"
            return _Outcome(ok=False, detail=detail)
        if not got_response:
            return _Outcome(ok=False, detail="stream ended without completion")
        return _Outcome(ok=True)
    except Exception as exc:
        db_session.rollback()
        return _Outcome(ok=False, detail=f"{type(exc).__name__}: {exc}")
    finally:
        try:
            session_manager.clear_turn_deadline(sandbox_id, session_id)
        except Exception:
            pass
        prompt_slot_cm.__exit__(None, None, None)


def _collect_outputs(
    session_manager: SessionManager,
    session_id: UUID,
    sandbox_id: UUID,
    user_id: UUID,
    loop: Any,
) -> list[dict[str, Any]]:
    """Read declared deliverables from the sandbox outputs/ manifest."""
    deliverables = (loop.playbook or {}).get("deliverables") or []
    artifacts = (
        session_manager.list_artifacts(session_id, user_id) or []
    )
    by_path = {str(a.get("path") or a.get("name") or ""): a for a in artifacts}
    outputs: list[dict[str, Any]] = []
    for declared in deliverables:
        declared = str(declared)
        path = declared
        if not path.startswith("outputs/"):
            path = f"outputs/{path.split('/')[-1]}"
        match = by_path.get(declared) or by_path.get(path) or by_path.get(
            path.removeprefix("outputs/")
        )
        if match is None:
            continue
        outputs.append(
            {
                "ship_action": "save_artifacts",
                "title": match.get("name") or declared,
                "summary": f"artifact at {match.get('path') or declared}",
            }
        )
    # Without declared deliverables, any artifact counts (agent-declared).
    if not outputs and artifacts:
        for artifact in artifacts[:10]:
            outputs.append(
                {
                    "ship_action": "save_artifacts",
                    "title": str(artifact.get("name") or "artifact"),
                    "summary": f"artifact at {artifact.get('path') or artifact.get('name')}",
                }
            )
    del sandbox_id
    return outputs


def _build_item_prompt(loop: Any, item: Any) -> str:
    playbook = loop.playbook or {}
    lines: list[str] = [f"# 循环任务：{loop.name}"]
    objective = playbook.get("objective")
    if objective:
        lines.append(f"\n目标：{objective}")
    lines.append(f"\n## 待处理条目\n- 标识：{item.source_key}")
    if item.source_summary:
        lines.append(f"- 摘要：{item.source_summary}")
    if item.attempts > 1:
        lines.append(f"- 第 {item.attempts} 次尝试")
    if item.guidance:
        lines.append(f"- 上次审核意见：{item.guidance}")
    deliverables = playbook.get("deliverables") or []
    if deliverables:
        lines.append("\n## 交付物（写入 outputs/ 目录）")
        lines.extend(f"- {d}" for d in deliverables)
    gates = playbook.get("quality_gates") or []
    if gates:
        lines.append("\n## 质量门")
        lines.extend(f"- {g}" for g in gates)
    lines.append("\n完成工作后，把全部交付物写入 outputs/ 并结束。")
    return "\n".join(lines)


def _max_attempts(loop: Any) -> int:
    return int((loop.caps or {}).get("max_item_attempts") or 3)


def _notify(
    db_session: Any,
    *,
    user_id: UUID,
    notif_type: NotificationType,
    title: str,
    description: str | None = None,
    additional_data: dict | None = None,
) -> None:
    try:
        create_notification(
            user_id,
            notif_type,
            db_session,
            title,
            description=description,
            additional_data=additional_data,
            autocommit=False,
        )
        # Best-effort IM push (approval cards / held outputs) to users
        # with a China IM binding; in-app notification above is the
        # durable channel, this is the reach channel.
        from onyx.onyxbot.china.framework import dispatch_im_notification

        dispatch_im_notification(
            user_id=user_id, title=title, description=description
        )
    except Exception:
        logger.exception("loop notification failed")


def _safe_fail(item_id: UUID, claim_token: str, detail: str) -> None:
    try:
        with get_session_with_current_tenant() as db_session:
            item = get_loop_item(db_session, item_id)
            if item is None or item.claim_token != claim_token:
                return
            loop = get_craft_loop_or_404(db_session, item.loop_id, for_update=True)
            record_work_failure(item, reason=detail, max_attempts=_max_attempts(loop))
            evaluate_governor(loop, fire_failed=True)
            db_session.commit()
    except Exception:
        logger.exception("safe-fail for loop item %s failed", item_id)
