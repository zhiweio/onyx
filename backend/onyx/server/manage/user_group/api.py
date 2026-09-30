"""Community Edition user group management API.

Mirrors the REST shapes the web admin UI and the integration test
manager speak (``/manage/admin/user-group``), backed by
``onyx.db.user_group_ce``.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from onyx.auth.permissions import require_permission
from onyx.db import user_group_ce
from onyx.db.engine.sql_engine import get_session
from onyx.db.enums import Permission
from onyx.db.models import User

router = APIRouter(prefix="/manage/admin/user-group")


class UserGroupCreateRequest(BaseModel):
    name: str
    user_ids: list[UUID] = Field(default_factory=list)
    cc_pair_ids: list[int] = Field(default_factory=list)


class UserGroupUpdateRequest(BaseModel):
    name: str | None = None


class UserGroupUsersRequest(BaseModel):
    user_ids: list[UUID]


class UserGroupPermissionsRequest(BaseModel):
    permissions: list[Permission]


class UserGroupManagerRequest(BaseModel):
    user_id: UUID
    is_manager: bool


def _serialize_group(group: Any) -> dict[str, Any]:
    return {
        "id": group.id,
        "name": group.name,
        "is_default": group.is_default,
        "users": [
            {
                "id": str(member.user.id),
                "email": member.user.email,
                "full_name": member.user.full_name,
                "is_manager": member.is_manager,
            }
            for member in group.users
        ],
        "cc_pairs": [
            {"id": pair.cc_pair_id} for pair in getattr(group, "cc_pairs", []) or []
        ],
        "document_sets": [
            {"id": ds.document_set_id}
            for ds in getattr(group, "document_sets", []) or []
        ],
        "personas": [
            {"id": persona.persona_id}
            for persona in getattr(group, "personas", []) or []
        ],
        "manager_ids": [
            str(member.user.id)
            for member in group.users
            if member.is_manager
        ],
    }


@router.get("")
def list_user_groups(
    include_default: bool = False,
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    return [
        _serialize_group(group)
        for group in user_group_ce.fetch_user_groups(
            db_session, include_default=include_default
        )
    ]


@router.post("")
def create_user_group(
    request: UserGroupCreateRequest,
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> dict[str, Any]:
    group = user_group_ce.create_user_group(
        db_session, name=request.name, user_ids=request.user_ids
    )
    return _serialize_group(group)


@router.patch("/{group_id}")
def update_user_group(
    group_id: int,
    request: UserGroupUpdateRequest,
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> dict[str, Any]:
    group = user_group_ce.fetch_user_group_or_404(db_session, group_id)
    if request.name is not None:
        group = user_group_ce.update_user_group_name(db_session, group_id, request.name)
    return _serialize_group(group)


@router.delete("/{group_id}")
def delete_user_group(
    group_id: int,
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> dict[str, Any]:
    user_group_ce.delete_user_group(db_session, group_id)
    return {"success": True}


@router.post("/{group_id}/add-users")
def add_users(
    group_id: int,
    request: UserGroupUsersRequest,
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> dict[str, Any]:
    group = user_group_ce.add_users_to_group(
        db_session, group_id, request.user_ids
    )
    return _serialize_group(group)


@router.post("/{group_id}/remove-users")
def remove_users(
    group_id: int,
    request: UserGroupUsersRequest,
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> dict[str, Any]:
    group = user_group_ce.remove_users_from_group(
        db_session, group_id, request.user_ids
    )
    return _serialize_group(group)


@router.get("/{group_id}/permissions")
def get_permissions(
    group_id: int,
    include_non_toggleable: bool = False,
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> list[str]:
    del include_non_toggleable
    return [p.value for p in user_group_ce.get_group_permissions(db_session, group_id)]


@router.put("/{group_id}/permissions")
def set_permissions(
    group_id: int,
    request: UserGroupPermissionsRequest,
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> list[str]:
    permissions = user_group_ce.set_group_permissions(
        db_session, group_id, request.permissions
    )
    return [p.value for p in permissions]


@router.put("/{group_id}/manager")
def set_manager(
    group_id: int,
    request: UserGroupManagerRequest,
    user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> dict[str, Any]:
    group = user_group_ce.fetch_user_group_or_404(db_session, group_id)
    link = next(
        (
            member
            for member in group.users
            if str(member.user.id) == str(request.user_id)
        ),
        None,
    )
    if link is None:
        from onyx.error_handling.error_codes import OnyxErrorCode
        from onyx.error_handling.exceptions import OnyxError

        raise OnyxError(
            OnyxErrorCode.NOT_FOUND,
            "Target user must already be a group member",
        )
    link.is_manager = request.is_manager
    db_session.commit()
    return _serialize_group(group)
