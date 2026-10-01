"""Community Edition user group management API.

Mirrors the REST shapes the web admin UI and the integration test
manager speak (``/manage/admin/user-group``), backed by
``onyx.db.user_group_ce``.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from onyx.auth.permission_projection import user_group_permissions
from onyx.auth.permissions import (
    PermissionAuthority,
    has_permission,
    require_permission,
)
from onyx.auth.scoped_permissions import get_scoped_groups
from onyx.db import user_group_ce
from onyx.db.engine.sql_engine import get_session
from onyx.db.enums import Permission
from onyx.db.models import (
    User,
    User__UserGroup,
    UserGroup__ConnectorCredentialPair,
)
from onyx.db.permissions import recompute_user_permissions__no_commit

router = APIRouter(prefix="/manage/admin/user-group")


class UserGroupCreateRequest(BaseModel):
    name: str
    user_ids: list[UUID] = Field(default_factory=list)
    cc_pair_ids: list[int] = Field(default_factory=list)


class UserGroupUpdateRequest(BaseModel):
    name: str | None = None
    user_ids: list[UUID] | None = None
    cc_pair_ids: list[int] | None = None


class UserGroupUsersRequest(BaseModel):
    user_ids: list[UUID]


class UserGroupPermissionsRequest(BaseModel):
    permissions: list[Permission]


class UserGroupManagerRequest(BaseModel):
    user_id: UUID
    is_manager: bool


def _serialize_group(
    group: Any,
    *,
    can_manage: bool = False,
    is_user_groups_admin: bool = False,
    is_full_admin: bool = False,
) -> dict[str, Any]:
    # group.users is a plain secondary many-to-many of User rows; the manager
    # flag lives on the User__UserGroup association rows.
    is_manager_by_user_id = {
        rel.user_id: rel.is_manager
        for rel in getattr(group, "user_group_relationships", []) or []
        if rel.user_id is not None
    }
    return {
        "id": group.id,
        "name": group.name,
        "is_default": group.is_default,
        "is_up_to_date": group.is_up_to_date,
        "is_up_for_deletion": group.is_up_for_deletion,
        "incognito_enabled": group.incognito_enabled,
        # Server-stamped affordance map; the frontend fails closed on absence.
        "permissions": user_group_permissions(
            can_manage=can_manage,
            is_user_groups_admin=is_user_groups_admin,
            is_full_admin=is_full_admin,
            is_default=group.is_default,
        ),
        "users": [
            {
                "id": str(member.id),
                "email": member.email,
                "is_manager": is_manager_by_user_id.get(member.id, False),
            }
            for member in group.users
        ],
        "cc_pairs": [{"id": pair.id} for pair in getattr(group, "cc_pairs", []) or []],
        "document_sets": [
            {"id": ds.id} for ds in getattr(group, "document_sets", []) or []
        ],
        "personas": [
            {"id": persona.id} for persona in getattr(group, "personas", []) or []
        ],
        "manager_ids": [
            str(user_id)
            for user_id, is_manager in is_manager_by_user_id.items()
            if is_manager
        ],
    }


@router.get("")
def list_user_groups(
    include_default: bool = False,
    user: User = Depends(
        require_permission(Permission.READ_USER_GROUPS, allow_scope=True)
    ),
    db_session: Session = Depends(get_session),
) -> list[dict[str, Any]]:
    # Read route is READ_USER_GROUPS-scoped (GATE 1 admits scoped managers);
    # per-group reach is decided by the stamped `permissions` map (GATE 2).
    is_full_admin = (
        has_permission(user, Permission.FULL_ADMIN_PANEL_ACCESS)
        is PermissionAuthority.GLOBAL
    )
    is_user_groups_admin = (
        has_permission(user, Permission.MANAGE_USER_GROUPS)
        is PermissionAuthority.GLOBAL
    )
    managed_ids = (
        None
        if is_user_groups_admin
        else get_scoped_groups(
            user, db_session, permission=Permission.MANAGE_USER_GROUPS
        )
    )
    return [
        _serialize_group(
            group,
            can_manage=(is_user_groups_admin or group.id in (managed_ids or set())),
            is_user_groups_admin=is_user_groups_admin,
            is_full_admin=is_full_admin,
        )
        for group in user_group_ce.fetch_user_groups(
            db_session, include_default=include_default
        )
    ]


@router.post("")
def create_user_group(
    request: UserGroupCreateRequest,
    _user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> dict[str, Any]:
    group = user_group_ce.create_user_group(
        db_session, name=request.name, user_ids=request.user_ids
    )
    return _serialize_group(
        group, can_manage=True, is_user_groups_admin=True, is_full_admin=True
    )


@router.patch("/{group_id}")
def update_user_group(
    group_id: int,
    request: UserGroupUpdateRequest,
    _user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Full-state update: rename, replace membership, replace cc-pair links.

    Absent fields are left untouched; present lists replace wholesale. Group
    edits mark the group out-of-date so the permission-sync machinery runs.
    """
    group = user_group_ce.fetch_user_group_or_404(db_session, group_id)

    if request.name is not None and request.name != group.name:
        group = user_group_ce.update_user_group_name(db_session, group_id, request.name)

    if request.user_ids is not None:
        existing_links = db_session.scalars(
            select(User__UserGroup).where(User__UserGroup.user_group_id == group.id)
        ).all()
        desired_users = set(request.user_ids)
        for link in existing_links:
            if link.user_id not in desired_users:
                db_session.delete(link)
        current_users = {link.user_id for link in existing_links}
        for user_id in desired_users - current_users:
            db_session.add(User__UserGroup(user_group_id=group.id, user_id=user_id))

    if request.cc_pair_ids is not None:
        existing_links = db_session.scalars(
            select(UserGroup__ConnectorCredentialPair).where(
                UserGroup__ConnectorCredentialPair.user_group_id == group.id,
                UserGroup__ConnectorCredentialPair.is_current.is_(True),
            )
        ).all()
        desired_pairs = set(request.cc_pair_ids)
        for link in existing_links:
            if link.cc_pair_id not in desired_pairs:
                db_session.delete(link)
        current_pairs = {link.cc_pair_id for link in existing_links}
        for cc_pair_id in desired_pairs - current_pairs:
            db_session.add(
                UserGroup__ConnectorCredentialPair(
                    user_group_id=group.id, cc_pair_id=cc_pair_id, is_current=True
                )
            )

    if db_session.is_modified(group) or db_session.dirty or db_session.new:
        group.is_up_to_date = False

    db_session.commit()
    db_session.refresh(group)
    return _serialize_group(
        group, can_manage=True, is_user_groups_admin=True, is_full_admin=True
    )


@router.delete("/{group_id}")
def delete_user_group(
    group_id: int,
    _user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> dict[str, Any]:
    user_group_ce.delete_user_group(db_session, group_id)
    return {"success": True}


@router.post("/{group_id}/add-users")
def add_users(
    group_id: int,
    request: UserGroupUsersRequest,
    _user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> dict[str, Any]:
    group = user_group_ce.add_users_to_group(db_session, group_id, request.user_ids)
    return _serialize_group(
        group, can_manage=True, is_user_groups_admin=True, is_full_admin=True
    )


@router.post("/{group_id}/remove-users")
def remove_users(
    group_id: int,
    request: UserGroupUsersRequest,
    _user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> dict[str, Any]:
    group = user_group_ce.remove_users_from_group(
        db_session, group_id, request.user_ids
    )
    return _serialize_group(
        group, can_manage=True, is_user_groups_admin=True, is_full_admin=True
    )


@router.get("/{group_id}/permissions")
def get_permissions(
    group_id: int,
    include_non_toggleable: bool = False,
    _user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> list[str]:
    del include_non_toggleable
    return [p.value for p in user_group_ce.get_group_permissions(db_session, group_id)]


@router.put("/{group_id}/permissions")
def set_permissions(
    group_id: int,
    request: UserGroupPermissionsRequest,
    _user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
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
    _user: User = Depends(require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)),
    db_session: Session = Depends(get_session),
) -> dict[str, Any]:
    group = user_group_ce.fetch_user_group_or_404(db_session, group_id)
    # The manager flag lives on the (user, group) membership link, not on User.
    link = db_session.scalar(
        select(User__UserGroup).where(
            User__UserGroup.user_group_id == group.id,
            User__UserGroup.user_id == request.user_id,
        )
    )
    if link is None:
        from onyx.error_handling.error_codes import OnyxErrorCode
        from onyx.error_handling.exceptions import OnyxError

        raise OnyxError(
            OnyxErrorCode.NOT_FOUND,
            "Target user must already be a group member",
        )
    link.is_manager = request.is_manager
    # Refresh the cached User.is_group_manager flag so GATE 1 scoped-manager
    # classification reflects the new link immediately.
    recompute_user_permissions__no_commit([request.user_id], db_session)
    db_session.commit()
    return _serialize_group(
        group, can_manage=True, is_user_groups_admin=True, is_full_admin=True
    )
