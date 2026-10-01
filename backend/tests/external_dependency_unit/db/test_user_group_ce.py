"""External-dependency tests for the CE user group management layer.

Runs against a real PostgreSQL (same fixture as the rest of the db suite).
"""

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from onyx.db.enums import Permission
from onyx.db.models import User, User__UserGroup, UserGroup
from onyx.db.user_group_ce import (
    add_users_to_group,
    assign_user_to_groups_by_name,
    create_user_group,
    delete_user_group,
    effective_permissions_for_user,
    fetch_user_group,
    fetch_user_groups,
    get_group_permissions,
    remove_users_from_group,
    set_group_permissions,
    update_user_group_name,
)
from onyx.error_handling.exceptions import OnyxError
from tests.external_dependency_unit.db.conftest import create_test_user


def _make_user(db_session: Session, label: str) -> User:
    return create_test_user(
        db_session, f"ug_{label}_{uuid4().hex[:8]}", assign_default_group=False
    )


def test_create_list_rename_delete_roundtrip(db_session: Session) -> None:
    group = create_user_group(db_session, name=f"组-{uuid4().hex[:6]}")
    try:
        assert fetch_user_group(db_session, group.id) is not None
        assert any(g.id == group.id for g in fetch_user_groups(db_session))

        renamed = update_user_group_name(
            db_session, group.id, f"组改-{uuid4().hex[:6]}"
        )
        assert renamed.name.startswith("组改-")
    finally:
        delete_user_group(db_session, group.id)
    assert fetch_user_group(db_session, group.id) is None


def test_duplicate_name_rejected(db_session: Session) -> None:
    name = f"重名-{uuid4().hex[:6]}"
    group = create_user_group(db_session, name=name)
    try:
        with pytest.raises(OnyxError):
            create_user_group(db_session, name=name)
    finally:
        delete_user_group(db_session, group.id)


def test_membership_add_remove_idempotent(db_session: Session) -> None:
    user = _make_user(db_session, "member")
    group = create_user_group(db_session, name=f"成员组-{uuid4().hex[:6]}")
    try:
        group = add_users_to_group(db_session, group.id, [user.id])
        assert {str(u.id) for u in group.users} == {str(user.id)}
        # adding again is a no-op
        group = add_users_to_group(db_session, group.id, [user.id])
        assert len(group.users) == 1
        group = remove_users_from_group(db_session, group.id, [user.id])
        assert group.users == []
    finally:
        delete_user_group(db_session, group.id)


def test_permissions_replace_and_resolve(db_session: Session) -> None:
    user = _make_user(db_session, "perm")
    group = create_user_group(
        db_session, name=f"权限组-{uuid4().hex[:6]}", user_ids=[user.id]
    )
    try:
        set_group_permissions(db_session, group.id, [Permission.MANAGE_LLMS])
        assert get_group_permissions(db_session, group.id) == [Permission.MANAGE_LLMS]
        effective = effective_permissions_for_user(db_session, user)
        assert Permission.MANAGE_LLMS in effective

        set_group_permissions(db_session, group.id, [])
        assert get_group_permissions(db_session, group.id) == []
    finally:
        delete_user_group(db_session, group.id)


def test_default_groups_are_membership_only(db_session: Session) -> None:
    defaults = db_session.scalars(
        select(UserGroup).where(UserGroup.is_default.is_(True))
    ).all()
    if not defaults:
        pytest.skip("default groups not seeded in this database")
    with pytest.raises(OnyxError):
        delete_user_group(db_session, defaults[0].id)


def test_assign_user_to_groups_by_name_creates_and_links(db_session: Session) -> None:
    user = _make_user(db_session, "sync")
    suffix = uuid4().hex[:6]
    groups = assign_user_to_groups_by_name(
        db_session,
        user_email=user.email,
        group_names=[f"财务部-{suffix}", f"税务组-{suffix}", "  "],
    )
    db_session.commit()
    try:
        assert len(groups) == 2
        links = db_session.scalars(
            select(User__UserGroup).where(User__UserGroup.user_id == user.id)
        ).all()
        link_group_ids = {link.user_group_id for link in links}
        for group in groups:
            assert group.id in link_group_ids
        # re-running is idempotent
        again = assign_user_to_groups_by_name(
            db_session, user_email=user.email, group_names=[f"财务部-{suffix}"]
        )
        assert again == []
    finally:
        for group in groups:
            db_session.delete(group)
        db_session.commit()
