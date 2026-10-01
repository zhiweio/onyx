"""Community Edition token rate limit admin API.

Re-exposes the (fully present in CE) enforcement layer over the REST
shapes the existing frontend panel speaks: /global, /users, /user-group
list+create, and shared update/delete by id.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from onyx.auth.permissions import require_permission
from onyx.db.engine.sql_engine import get_session
from onyx.db.enums import Permission
from onyx.db.models import (
    TokenRateLimit,
    TokenRateLimit__UserGroup,
    User,
)
from onyx.db.token_limit import (
    delete_token_rate_limit,
    fetch_all_global_token_rate_limits,
    fetch_all_user_token_rate_limits,
    insert_global_token_rate_limit,
    insert_user_token_rate_limit,
    update_token_rate_limit,
)
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.server.token_rate_limits.models import (
    TokenRateLimitArgs,
    TokenRateLimitDisplay,
    TokenRateLimitUpdateArgs,
)

router = APIRouter(prefix="/admin/token-rate-limits")


def _display(row: TokenRateLimit) -> TokenRateLimitDisplay:
    return TokenRateLimitDisplay(
        token_id=row.id,
        enabled=row.enabled,
        token_budget=row.token_budget,
        period_hours=row.period_hours,
        cost_budget_cents=row.cost_budget_cents,
    )


@router.get("/global")
def list_global(
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),  # noqa: ARG001
    db_session: Session = Depends(get_session),
) -> list[TokenRateLimitDisplay]:
    return [_display(row) for row in fetch_all_global_token_rate_limits(db_session)]


@router.get("/users")
def list_users(
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),  # noqa: ARG001
    db_session: Session = Depends(get_session),
) -> list[TokenRateLimitDisplay]:
    return [_display(row) for row in fetch_all_user_token_rate_limits(db_session)]


@router.get("/user-groups")
def list_user_group(
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),  # noqa: ARG001
    db_session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    rows = db_session.scalars(select(TokenRateLimit__UserGroup)).all()
    return [
        {
            "token_id": row.rate_limit_id,
            "group_id": row.user_group_id,
        }
        for row in rows
    ]


@router.get("/user-group/{group_id}")
def list_for_group(
    group_id: int,
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),  # noqa: ARG001
    db_session: Session = Depends(get_session),
) -> list[TokenRateLimitDisplay]:
    rows = db_session.scalars(
        select(TokenRateLimit)
        .join(
            TokenRateLimit__UserGroup,
            TokenRateLimit__UserGroup.rate_limit_id == TokenRateLimit.id,
        )
        .where(TokenRateLimit__UserGroup.user_group_id == group_id)
    ).all()
    return [_display(row) for row in rows]


@router.post("/global")
def create_global(
    args: TokenRateLimitArgs,
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),  # noqa: ARG001
    db_session: Session = Depends(get_session),
) -> TokenRateLimitDisplay:
    return _display(insert_global_token_rate_limit(db_session, args))


@router.post("/users")
def create_user(
    args: TokenRateLimitArgs,
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),  # noqa: ARG001
    db_session: Session = Depends(get_session),
) -> TokenRateLimitDisplay:
    return _display(insert_user_token_rate_limit(db_session, args))


@router.post("/user-group/{group_id}")
def create_user_group(
    group_id: int,
    args: TokenRateLimitArgs,
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),  # noqa: ARG001
    db_session: Session = Depends(get_session),
) -> TokenRateLimitDisplay:
    row = insert_user_token_rate_limit(db_session, args)
    db_session.add(
        TokenRateLimit__UserGroup(rate_limit_id=row.id, user_group_id=group_id)
    )
    db_session.commit()
    return _display(row)


@router.put("/rate-limit/{token_rate_limit_id}")
def update(
    token_rate_limit_id: int,
    args: TokenRateLimitUpdateArgs,
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),  # noqa: ARG001
    db_session: Session = Depends(get_session),
) -> TokenRateLimitDisplay:
    try:
        row = update_token_rate_limit(db_session, token_rate_limit_id, args)
    except ValueError as exc:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, str(exc)) from exc
    return _display(row)


@router.delete("/rate-limit/{token_rate_limit_id}")
def remove(
    token_rate_limit_id: int,
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),  # noqa: ARG001
    db_session: Session = Depends(get_session),
) -> dict[str, Any]:
    try:
        delete_token_rate_limit(db_session, token_rate_limit_id)
    except ValueError as exc:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, str(exc)) from exc
    return {"success": True}
