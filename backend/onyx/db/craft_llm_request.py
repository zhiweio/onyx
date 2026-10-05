"""Per-request LLM ledger for craft sessions.

The harness reports each assistant message's usage several times
(``message.updated`` fires per step with cumulative-or-updated numbers), so
``upsert_craft_llm_request`` keys on (session_id, opencode_message_id) and
reports whether the row is new. Only new rows feed the daily user_usage
rollup — replayed events never double-count.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from onyx.db.models import CraftLLMRequest


def upsert_craft_llm_request(
    db_session: Session,
    *,
    session_id: UUID | None,
    turn_index: int | None,
    opencode_message_id: str,
    provider: str | None,
    model: str | None,
    input_tokens: int,
    output_tokens: int,
    reasoning_tokens: int,
    cache_read_tokens: int,
    cache_write_tokens: int,
    cost: float | None,
) -> bool:
    """Insert one request row; update in place when the message repeats.

    Returns True when the row was newly created (the caller may add it to
    the daily rollup), False when an existing row was refreshed. The
    pre-check is safe here because one turn runner serializes a session's
    writes; the ON CONFLICT upsert stays as the concurrent-writer backstop.
    """
    existing = db_session.execute(
        select(CraftLLMRequest.id).where(
            CraftLLMRequest.session_id == session_id,
            CraftLLMRequest.opencode_message_id == opencode_message_id,
        )
    ).first()
    stmt = pg_insert(CraftLLMRequest).values(
        session_id=session_id,
        turn_index=turn_index,
        opencode_message_id=opencode_message_id,
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
        cost=cost,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_craft_llm_request_session_message",
        set_={
            "turn_index": stmt.excluded.turn_index,
            "provider": stmt.excluded.provider,
            "model": stmt.excluded.model,
            "input_tokens": stmt.excluded.input_tokens,
            "output_tokens": stmt.excluded.output_tokens,
            "reasoning_tokens": stmt.excluded.reasoning_tokens,
            "cache_read_tokens": stmt.excluded.cache_read_tokens,
            "cache_write_tokens": stmt.excluded.cache_write_tokens,
            "cost": stmt.excluded.cost,
        },
    )
    db_session.execute(stmt)
    return existing is None


def session_llm_usage_totals(
    db_session: Session, session_ids: list[UUID]
) -> dict[str, dict[str, float]]:
    """Token/cost totals per session id (string keys), for job roll-ups."""
    if not session_ids:
        return {}
    from sqlalchemy import func, select

    rows = db_session.execute(
        select(
            CraftLLMRequest.session_id,
            func.sum(CraftLLMRequest.input_tokens),
            func.sum(CraftLLMRequest.output_tokens),
            func.sum(CraftLLMRequest.reasoning_tokens),
            func.sum(CraftLLMRequest.cache_read_tokens),
            func.sum(CraftLLMRequest.cache_write_tokens),
            func.sum(CraftLLMRequest.cost),
        )
        .where(CraftLLMRequest.session_id.in_(session_ids))
        .group_by(CraftLLMRequest.session_id)
    ).all()
    totals: dict[str, dict[str, float]] = {}
    for row in rows:
        if row[0] is None:
            continue
        totals[str(row[0])] = {
            "input_tokens": float(row[1] or 0),
            "output_tokens": float(row[2] or 0),
            "reasoning_tokens": float(row[3] or 0),
            "cache_read_tokens": float(row[4] or 0),
            "cache_write_tokens": float(row[5] or 0),
            "cost": float(row[6] or 0.0),
        }
    return totals
