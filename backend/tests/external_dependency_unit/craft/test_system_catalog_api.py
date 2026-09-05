"""Route-level checks for the gallery and admin catalog endpoints.

Handlers are called directly with an explicit session and user, matching the
existing craft route tests. The permission dependencies themselves are covered
by the shared ``require_permission`` tests; what matters here is that the
gallery hides unpublished content and that admin writes reach the catalog.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from onyx.db.enums import SystemCatalogCategory, SystemCatalogPublishStatus
from onyx.db.models import Skill, SystemSkill, User
from onyx.db.system_catalog.skill import create_system_skill
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.server.features.system_catalog.admin_api import (
    delete_catalog_skill,
    get_catalog_skill,
    list_catalog_skills,
    patch_catalog_skill,
    publish_catalog_skill,
    unpublish_catalog_skill,
)
from onyx.server.features.system_catalog.gallery_api import (
    fork_gallery_skill,
    get_gallery_skill,
    list_gallery_skills,
)
from onyx.server.features.system_catalog.models import (
    PublishRequest,
    SystemSkillPatchRequest,
)
from tests.external_dependency_unit.conftest import create_test_user

BUILT_IN_CONTENT_ID = "doc-review"


@pytest.fixture
def gallery_user(db_session: Session) -> User:
    return create_test_user(db_session, "gallery")


@pytest.fixture
def draft_entry(
    db_session: Session, request: pytest.FixtureRequest
) -> Generator[SystemSkill, None, None]:
    slug = f"api-{abs(hash(request.node.name)) % 10**8}"
    entry = create_system_skill(
        db_session,
        slug=slug,
        name=slug,
        description="Route test entry.",
        category=SystemCatalogCategory.OFFICE,
        tags=["route"],
        built_in_skill_id=BUILT_IN_CONTENT_ID,
    )
    db_session.commit()
    yield entry
    db_session.execute(delete(Skill).where(Skill.system_skill_id == entry.id))
    db_session.execute(delete(SystemSkill).where(SystemSkill.id == entry.id))
    db_session.commit()


def _gallery_ids(db_session: Session, user: User) -> set:
    response = list_gallery_skills(
        q=None, category=None, tags=None, _=user, db_session=db_session
    )
    return {item.id for item in response.items}


def test_gallery_hides_drafts_and_serves_published(
    db_session: Session, draft_entry: SystemSkill, gallery_user: User
) -> None:
    assert draft_entry.id not in _gallery_ids(db_session, gallery_user)

    with pytest.raises(OnyxError) as caught:
        get_gallery_skill(draft_entry.id, _=gallery_user, db_session=db_session)
    assert caught.value.error_code is OnyxErrorCode.NOT_FOUND

    publish_catalog_skill(
        draft_entry.id,
        PublishRequest(changelog="published"),
        user=gallery_user,
        db_session=db_session,
    )

    assert draft_entry.id in _gallery_ids(db_session, gallery_user)
    detail = get_gallery_skill(draft_entry.id, _=gallery_user, db_session=db_session)
    assert detail.instructions_markdown
    assert detail.is_built_in_content is True


def test_gallery_hides_entries_again_after_unpublish(
    db_session: Session, draft_entry: SystemSkill, gallery_user: User
) -> None:
    publish_catalog_skill(
        draft_entry.id,
        PublishRequest(changelog=""),
        user=gallery_user,
        db_session=db_session,
    )
    assert draft_entry.id in _gallery_ids(db_session, gallery_user)

    unpublish_catalog_skill(draft_entry.id, _=gallery_user, db_session=db_session)

    assert draft_entry.id not in _gallery_ids(db_session, gallery_user)


def test_fork_endpoint_returns_a_user_owned_copy(
    db_session: Session, draft_entry: SystemSkill, gallery_user: User
) -> None:
    publish_catalog_skill(
        draft_entry.id,
        PublishRequest(changelog=""),
        user=gallery_user,
        db_session=db_session,
    )

    forked = fork_gallery_skill(
        draft_entry.id, user=gallery_user, db_session=db_session
    )

    copy = db_session.get(Skill, forked.id)
    assert copy is not None
    assert copy.author_user_id == gallery_user.id
    assert copy.system_skill_id == draft_entry.id


def test_admin_list_includes_drafts(
    db_session: Session, draft_entry: SystemSkill, gallery_user: User
) -> None:
    response = list_catalog_skills(
        q=None, category=None, status=None, _=gallery_user, db_session=db_session
    )
    assert draft_entry.id in {item.id for item in response.items}


def test_admin_patch_updates_metadata_without_republishing(
    db_session: Session, draft_entry: SystemSkill, gallery_user: User
) -> None:
    publish_catalog_skill(
        draft_entry.id,
        PublishRequest(changelog=""),
        user=gallery_user,
        db_session=db_session,
    )
    version_after_publish = draft_entry.version

    patch_catalog_skill(
        draft_entry.id,
        SystemSkillPatchRequest(
            description="Edited.", category=SystemCatalogCategory.TAX
        ),
        _=gallery_user,
        db_session=db_session,
    )

    refreshed = get_catalog_skill(draft_entry.id, _=gallery_user, db_session=db_session)
    assert refreshed.description == "Edited."
    assert refreshed.category is SystemCatalogCategory.TAX
    # Edits stay in the catalog until the admin publishes again, so the live
    # projection keeps serving what was last published.
    assert refreshed.version == version_after_publish
    detail = get_gallery_skill(draft_entry.id, _=gallery_user, db_session=db_session)
    assert detail.description == "Edited."


def test_admin_cannot_delete_a_published_entry(
    db_session: Session, draft_entry: SystemSkill, gallery_user: User
) -> None:
    publish_catalog_skill(
        draft_entry.id,
        PublishRequest(changelog=""),
        user=gallery_user,
        db_session=db_session,
    )

    with pytest.raises(OnyxError) as caught:
        delete_catalog_skill(draft_entry.id, _=gallery_user, db_session=db_session)
    assert caught.value.error_code is OnyxErrorCode.CONFLICT

    unpublish_catalog_skill(draft_entry.id, _=gallery_user, db_session=db_session)
    delete_catalog_skill(draft_entry.id, _=gallery_user, db_session=db_session)
    assert db_session.get(SystemSkill, draft_entry.id) is None


def test_publish_bumps_version_and_records_the_changelog(
    db_session: Session, draft_entry: SystemSkill, gallery_user: User
) -> None:
    first = publish_catalog_skill(
        draft_entry.id,
        PublishRequest(changelog="initial release"),
        user=gallery_user,
        db_session=db_session,
    )
    assert first.version == 1
    assert first.changelog == "initial release"
    assert first.publish_status is SystemCatalogPublishStatus.PUBLISHED

    second = publish_catalog_skill(
        draft_entry.id,
        PublishRequest(changelog="fixed a typo"),
        user=gallery_user,
        db_session=db_session,
    )
    assert second.version == 2
    assert second.changelog == "fixed a typo"
