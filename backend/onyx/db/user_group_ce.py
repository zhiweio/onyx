"""Community Edition user group management.

The schema (``user_group``, ``user__user_group``, ``permission_grants``)
has always lived in the CE migration chain; this module supplies the
management operations a Community deployment needs, written against the
public API behavior (CRUD shapes the web UI and integration tests speak)
rather than any Enterprise implementation.

Default groups (Admin/Basic) keep the invariants from
``onyx.db.user_group``: membership only.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from onyx.db.enums import Permission
from onyx.db.models import (
    PermissionGrant,
    User,
    UserGroup,
    User__UserGroup,
)
from onyx.db.user_group import (
    assert_group_config_is_editable,
    assert_groups_config_are_editable,
)
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError


def fetch_user_group(db_session: Session, group_id: int) -> UserGroup | None:
    return db_session.scalar(select(UserGroup).where(UserGroup.id == group_id))


def fetch_user_group_or_404(db_session: Session, group_id: int) -> UserGroup:
    group = fetch_user_group(db_session, group_id)
    if group is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, f"User group {group_id} not found")
    return group


def fetch_user_groups(
    db_session: Session, include_default: bool = False
) -> list[UserGroup]:
    stmt = select(UserGroup).order_by(UserGroup.id)
    if not include_default:
        stmt = stmt.where(UserGroup.is_default.is_(False))
    return list(db_session.scalars(stmt).all())


def create_user_group(
    db_session: Session,
    *,
    name: str,
    user_ids: Sequence[UUID] = (),
) -> UserGroup:
    name = name.strip()
    if not name:
        raise OnyxError(OnyxErrorCode.VALIDATION_ERROR, "Group name is required")
    clash = db_session.scalar(select(UserGroup.id).where(UserGroup.name == name))
    if clash is not None:
        raise OnyxError(OnyxErrorCode.CONFLICT, f"Group {name!r} already exists")
    group = UserGroup(name=name)
    db_session.add(group)
    db_session.flush()
    for user_id in user_ids:
        add_user_to_group__no_commit(db_session, group, user_id)
    db_session.commit()
    return group


def update_user_group_name(db_session: Session, group_id: int, name: str) -> UserGroup:
    group = fetch_user_group_or_404(db_session, group_id)
    assert_group_config_is_editable(db_session, group.id, "rename")
    name = name.strip()
    if not name:
        raise OnyxError(OnyxErrorCode.VALIDATION_ERROR, "Group name is required")
    clash = db_session.scalar(
        select(UserGroup.id).where(UserGroup.name == name, UserGroup.id != group.id)
    )
    if clash is not None:
        raise OnyxError(OnyxErrorCode.CONFLICT, f"Group {name!r} already exists")
    group.name = name
    db_session.commit()
    return group


def delete_user_group(db_session: Session, group_id: int) -> None:
    group = fetch_user_group_or_404(db_session, group_id)
    assert_group_config_is_editable(db_session, group.id, "delete")
    db_session.delete(group)
    db_session.commit()


def add_user_to_group__no_commit(
    db_session: Session, group: UserGroup, user_id: UUID
) -> bool:
    existing = db_session.scalar(
        select(User__UserGroup.id).where(
            User__UserGroup.user_id == user_id,
            User__UserGroup.user_group_id == group.id,
        )
    )
    if existing is not None:
        return False
    user = db_session.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, f"User {user_id} not found")
    db_session.add(User__UserGroup(user_id=user_id, user_group_id=group.id))
    return True


def add_users_to_group(db_session: Session, group_id: int, user_ids: Sequence[UUID]) -> UserGroup:
    group = fetch_user_group_or_404(db_session, group_id)
    for user_id in user_ids:
        add_user_to_group__no_commit(db_session, group, user_id)
    db_session.commit()
    db_session.refresh(group)
    return group


def remove_users_from_group(
    db_session: Session, group_id: int, user_ids: Sequence[UUID]
) -> UserGroup:
    group = fetch_user_group_or_404(db_session, group_id)
    removed = db_session.scalars(
        select(User__UserGroup).where(
            User__UserGroup.user_group_id == group.id,
            User__UserGroup.user_id.in_(user_ids),
        )
    ).all()
    for link in removed:
        db_session.delete(link)
    db_session.commit()
    db_session.refresh(group)
    return group


def set_group_permissions(
    db_session: Session, group_id: int, permissions: Collection[Permission]
) -> list[Permission]:
    """Replace the group's permission grants with the given set."""
    group = fetch_user_group_or_404(db_session, group_id)
    assert_group_config_is_editable(db_session, group.id, "set permissions on")
    for grant in list(group.permission_grants):
        db_session.delete(grant)
    for permission in permissions:
        db_session.add(PermissionGrant(group_id=group.id, permission=permission))
    db_session.commit()
    db_session.refresh(group)
    return [grant.permission for grant in group.permission_grants]


def get_group_permissions(db_session: Session, group_id: int) -> list[Permission]:
    group = fetch_user_group_or_404(db_session, group_id)
    return [grant.permission for grant in group.permission_grants]


def effective_permissions_for_user(db_session: Session, user: User) -> list[Permission]:
    """Union of the user's groups' grants, expanded with implied permissions."""
    from onyx.auth.permissions import resolve_effective_permissions

    group_ids = [
        link.user_group_id
        for link in db_session.scalars(
            select(User__UserGroup).where(User__UserGroup.user_id == user.id)
        ).all()
    ]
    if not group_ids:
        return []
    granted = {
        grant.permission.value
        for group in db_session.scalars(
            select(UserGroup).where(UserGroup.id.in_(group_ids))
        ).all()
        for grant in group.permission_grants
    }
    return sorted(resolve_effective_permissions(granted))


# ── org sync entry point ─────────────────────────────────────────────────


def assign_user_to_groups_by_name(
    db_session: Session, *, user_email: str, group_names: Sequence[str]
) -> list[UserGroup]:
    """Ensure ``user_email`` belongs to one group per name (created if
    missing). Used by China SSO org sync to map platform departments onto
    groups. Commits nothing — the caller owns the transaction.
    """
    user = db_session.scalar(select(User).where(User.email == user_email))
    if user is None:
        return []
    assigned: list[UserGroup] = []
    for name in group_names:
        name = name.strip()
        if not name:
            continue
        group = db_session.scalar(select(UserGroup).where(UserGroup.name == name))
        if group is None:
            group = UserGroup(name=name)
            db_session.add(group)
            db_session.flush()
        if add_user_to_group__no_commit(db_session, group, user.id):
            assigned.append(group)
    return assigned
