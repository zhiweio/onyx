"""System catalog lifecycle: publish, unpublish, fork, and version drift.

These cover the invariants the projection model rests on:

- a draft is invisible to users and has no runtime row;
- publishing creates exactly one workspace-owned runtime row and republishing
  updates it in place rather than adding a second one;
- unpublishing drops that row but leaves user forks untouched;
- a fork is an independent, user-owned row that records where it came from.
"""

from __future__ import annotations

from collections.abc import Generator
from uuid import UUID

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from onyx.db.enums import (
    SystemCatalogCategory,
    SystemCatalogPublishStatus,
)
from onyx.db.models import (
    ReportTemplate,
    Scenario,
    Skill,
    SystemReportTemplate,
    SystemScenario,
    SystemSkill,
    User,
)
from onyx.db.system_catalog.constants import require_published
from onyx.db.system_catalog.fork import (
    fork_system_report_template_for_user,
    fork_system_scenario_for_user,
    fork_system_skill_for_user,
)
from onyx.db.system_catalog.publish import (
    find_projected_report_template,
    find_projected_scenario,
    find_projected_skill,
    publish_system_report_template,
    publish_system_scenario,
    publish_system_skill,
    unpublish_system_report_template,
    unpublish_system_scenario,
    unpublish_system_skill,
)
from onyx.db.system_catalog.report_template import create_system_report_template
from onyx.db.system_catalog.scenario import create_system_scenario
from onyx.db.system_catalog.skill import create_system_skill, list_system_skills
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from tests.external_dependency_unit.conftest import create_test_user

# Content that ships on disk, so the projection is bundle-free and the fork
# path exercises the "package a built-in directory" branch.
BUILT_IN_CONTENT_ID = "docx"


@pytest.fixture
def catalog_user(db_session: Session) -> User:
    return create_test_user(db_session, "catalog")


@pytest.fixture
def catalog_skill(
    db_session: Session, unique_slug: str
) -> Generator[SystemSkill, None, None]:
    entry = create_system_skill(
        db_session,
        slug=unique_slug,
        name=unique_slug,
        description="A catalog skill under test.",
        category=SystemCatalogCategory.OFFICE,
        tags=["testing"],
        built_in_skill_id=BUILT_IN_CONTENT_ID,
    )
    db_session.commit()
    yield entry
    _purge_catalog_skill(db_session, entry.id)


@pytest.fixture
def unique_slug(request: pytest.FixtureRequest) -> str:
    # Slugs are globally unique and the suite shares one database, so derive a
    # per-test slug instead of a constant.
    raw = request.node.name.lower().replace("_", "-")
    return f"cat-{abs(hash(raw)) % 10**8}"


def _purge_catalog_skill(db_session: Session, entry_id: UUID) -> None:
    db_session.execute(delete(Skill).where(Skill.system_skill_id == entry_id))
    db_session.execute(delete(SystemSkill).where(SystemSkill.id == entry_id))
    db_session.commit()


def test_draft_entry_has_no_projection_and_is_hidden(
    db_session: Session, catalog_skill: SystemSkill
) -> None:
    assert catalog_skill.publish_status is SystemCatalogPublishStatus.DRAFT
    assert catalog_skill.version == 0
    assert find_projected_skill(db_session, catalog_skill) is None

    with pytest.raises(OnyxError) as caught:
        require_published(catalog_skill)
    assert caught.value.error_code is OnyxErrorCode.NOT_FOUND

    published = list_system_skills(
        db_session, statuses=[SystemCatalogPublishStatus.PUBLISHED]
    )
    assert catalog_skill.id not in {entry.id for entry in published}


def test_publish_creates_one_projection_and_republish_updates_it(
    db_session: Session, catalog_skill: SystemSkill, catalog_user: User
) -> None:
    projection = publish_system_skill(
        db_session, catalog_skill, publisher=catalog_user, changelog="first"
    )
    db_session.commit()

    assert catalog_skill.publish_status is SystemCatalogPublishStatus.PUBLISHED
    assert catalog_skill.version == 1
    assert projection.author_user_id is None
    assert projection.name == catalog_skill.slug
    assert projection.system_skill_version == 1

    catalog_skill.description = "Updated description."
    republished = publish_system_skill(
        db_session, catalog_skill, publisher=catalog_user, changelog="second"
    )
    db_session.commit()

    assert republished.id == projection.id
    assert catalog_skill.version == 2
    assert republished.description == "Updated description."
    assert republished.system_skill_version == 2

    rows = db_session.scalars(
        select(Skill).where(Skill.system_skill_id == catalog_skill.id)
    ).all()
    assert len(rows) == 1


def test_unpublish_drops_projection_but_keeps_forks(
    db_session: Session, catalog_skill: SystemSkill, catalog_user: User
) -> None:
    publish_system_skill(db_session, catalog_skill, publisher=catalog_user)
    db_session.commit()

    fork = fork_system_skill_for_user(db_session, catalog_skill, catalog_user)
    db_session.commit()
    fork_id = fork.id

    unpublish_system_skill(db_session, catalog_skill)
    db_session.commit()

    assert catalog_skill.publish_status is SystemCatalogPublishStatus.ARCHIVED
    assert find_projected_skill(db_session, catalog_skill) is None

    surviving = db_session.get(Skill, fork_id)
    assert surviving is not None
    assert surviving.author_user_id == catalog_user.id
    assert surviving.system_skill_id == catalog_skill.id


def test_fork_renames_to_avoid_collisions_and_records_source(
    db_session: Session, catalog_skill: SystemSkill, catalog_user: User
) -> None:
    publish_system_skill(db_session, catalog_skill, publisher=catalog_user)
    db_session.commit()

    first = fork_system_skill_for_user(db_session, catalog_skill, catalog_user)
    second = fork_system_skill_for_user(db_session, catalog_skill, catalog_user)
    db_session.commit()

    # The projection already owns the bare slug, and two enabled skills may not
    # share a name.
    assert first.name != catalog_skill.slug
    assert second.name != first.name

    for fork in (first, second):
        assert fork.author_user_id == catalog_user.id
        assert fork.built_in_skill_id is None
        assert fork.bundle_file_id is not None
        assert fork.system_skill_id == catalog_skill.id
        assert fork.system_skill_version == catalog_skill.version


def test_fork_of_unpublished_entry_is_rejected(
    db_session: Session, catalog_skill: SystemSkill, catalog_user: User
) -> None:
    with pytest.raises(OnyxError) as caught:
        fork_system_skill_for_user(db_session, catalog_skill, catalog_user)
    assert caught.value.error_code is OnyxErrorCode.NOT_FOUND


def test_fork_version_trails_after_upstream_republish(
    db_session: Session, catalog_skill: SystemSkill, catalog_user: User
) -> None:
    publish_system_skill(db_session, catalog_skill, publisher=catalog_user)
    db_session.commit()
    fork = fork_system_skill_for_user(db_session, catalog_skill, catalog_user)
    db_session.commit()

    assert fork.system_skill_version == catalog_skill.version

    publish_system_skill(
        db_session, catalog_skill, publisher=catalog_user, changelog="newer"
    )
    db_session.commit()

    assert fork.system_skill_version is not None
    assert fork.system_skill_version < catalog_skill.version


def test_report_template_fork_gets_a_free_slug(
    db_session: Session, catalog_user: User, unique_slug: str
) -> None:
    template_slug = unique_slug.replace("-", "_")
    entry = create_system_report_template(
        db_session,
        slug=template_slug,
        name="Catalog template",
        description="A template under test.",
        body="# Heading\n\n## Section\n",
        category=SystemCatalogCategory.OFFICE,
        tags=["testing"],
    )
    db_session.commit()
    try:
        projection = publish_system_report_template(
            db_session, entry, publisher=catalog_user
        )
        db_session.commit()
        assert projection.slug == entry.slug
        assert projection.author_user_id is None

        fork = fork_system_report_template_for_user(db_session, entry, catalog_user)
        db_session.commit()

        assert fork.slug != projection.slug
        assert fork.body == entry.body
        assert fork.author_user_id == catalog_user.id
        assert fork.system_report_template_version == entry.version
    finally:
        db_session.execute(
            delete(ReportTemplate).where(
                ReportTemplate.system_report_template_id == entry.id
            )
        )
        db_session.execute(
            delete(SystemReportTemplate).where(SystemReportTemplate.id == entry.id)
        )
        db_session.commit()


def test_report_template_unpublish_is_blocked_while_a_scenario_uses_it(
    db_session: Session, catalog_user: User, unique_slug: str
) -> None:
    template_slug = unique_slug.replace("-", "_")
    entry = create_system_report_template(
        db_session,
        slug=template_slug,
        name="Referenced template",
        description="A referenced template.",
        body="# Referenced\n",
        category=SystemCatalogCategory.OFFICE,
        tags=[],
    )
    db_session.commit()
    referencing = Scenario(
        name=f"references-{template_slug}",
        description="",
        author_user_id=catalog_user.id,
        rules={},
        report_template=template_slug,
    )
    try:
        publish_system_report_template(db_session, entry, publisher=catalog_user)
        db_session.add(referencing)
        db_session.commit()

        with pytest.raises(OnyxError) as caught:
            unpublish_system_report_template(db_session, entry)
        assert caught.value.error_code is OnyxErrorCode.CONFLICT
        db_session.rollback()
    finally:
        db_session.delete(referencing)
        db_session.commit()
        db_session.execute(
            delete(ReportTemplate).where(
                ReportTemplate.system_report_template_id == entry.id
            )
        )
        db_session.execute(
            delete(SystemReportTemplate).where(SystemReportTemplate.id == entry.id)
        )
        db_session.commit()


def test_scenario_publish_requires_its_skills_to_be_published(
    db_session: Session, catalog_skill: SystemSkill, catalog_user: User
) -> None:
    scenario_slug = f"{catalog_skill.slug}-pack"
    entry = create_system_scenario(
        db_session,
        slug=scenario_slug,
        name="Pack under test",
        description="A pack under test.",
        category=SystemCatalogCategory.OFFICE,
        tags=[],
        rules={"domain": "office"},
        skill_slugs=[catalog_skill.slug],
        report_template_slug=None,
    )
    db_session.commit()
    try:
        # The bound skill is still a draft, so the pack cannot resolve it.
        with pytest.raises(OnyxError) as caught:
            publish_system_scenario(db_session, entry, publisher=catalog_user)
        assert caught.value.error_code is OnyxErrorCode.INVALID_INPUT
        db_session.rollback()

        skill_projection = publish_system_skill(
            db_session, catalog_skill, publisher=catalog_user
        )
        projection = publish_system_scenario(db_session, entry, publisher=catalog_user)
        db_session.commit()

        assert projection.author_user_id is None
        assert [link.skill_id for link in projection.skill_links] == [
            skill_projection.id
        ]
        # Catalog rules name slugs; the runtime resolver needs skill UUIDs.
        assert projection.rules["always_skill_ids"] == [str(skill_projection.id)]

        fork = fork_system_scenario_for_user(db_session, entry, catalog_user)
        db_session.commit()
        assert fork.author_user_id == catalog_user.id
        assert [link.skill_id for link in fork.skill_links] == [skill_projection.id]

        unpublish_system_scenario(db_session, entry)
        db_session.commit()
        assert find_projected_scenario(db_session, entry) is None
        assert db_session.get(Scenario, fork.id) is not None
    finally:
        db_session.execute(
            delete(Scenario).where(Scenario.system_scenario_id == entry.id)
        )
        db_session.execute(delete(SystemScenario).where(SystemScenario.id == entry.id))
        db_session.commit()


def test_scenario_cannot_bind_a_user_private_report_template(
    db_session: Session, catalog_skill: SystemSkill, catalog_user: User
) -> None:
    """Binding a private template would leak it into everyone's SCENARIO.md.

    ``render_scenario_markdown_named`` resolves ``scenario.report_template``
    with a global slug lookup and splices the body in verbatim.
    """
    publish_system_skill(db_session, catalog_skill, publisher=catalog_user)
    private_slug = f"{catalog_skill.slug.replace('-', '_')}_private"
    private = ReportTemplate(
        slug=private_slug,
        name="A user's private template",
        description="",
        body="# Secret\n",
        author_user_id=catalog_user.id,
        is_builtin=False,
    )
    db_session.add(private)
    entry = create_system_scenario(
        db_session,
        slug=f"{catalog_skill.slug}-private-pack",
        name="Pack bound to a private template",
        description="A pack under test.",
        category=SystemCatalogCategory.OFFICE,
        tags=[],
        rules={},
        skill_slugs=[catalog_skill.slug],
        report_template_slug=None,
    )
    # Catalog writes reject unknown catalog slugs. The publish guard still
    # has to catch a private runtime slug assigned outside that path.
    entry.report_template_slug = private_slug
    db_session.commit()
    try:
        with pytest.raises(OnyxError) as caught:
            publish_system_scenario(db_session, entry, publisher=catalog_user)
        assert caught.value.error_code is OnyxErrorCode.INVALID_INPUT
        db_session.rollback()
        assert find_projected_scenario(db_session, entry) is None
    finally:
        db_session.execute(
            delete(Scenario).where(Scenario.system_scenario_id == entry.id)
        )
        db_session.execute(delete(SystemScenario).where(SystemScenario.id == entry.id))
        db_session.execute(
            delete(ReportTemplate).where(ReportTemplate.slug == private_slug)
        )
        db_session.commit()


def test_scenario_write_rejects_unknown_skill_slug(
    db_session: Session, unique_slug: str
) -> None:
    with pytest.raises(OnyxError) as caught:
        create_system_scenario(
            db_session,
            slug=f"{unique_slug}-pack",
            name="Broken pack",
            description="References a skill that is not in the catalog.",
            category=SystemCatalogCategory.OFFICE,
            tags=[],
            rules={},
            skill_slugs=["no-such-catalog-skill"],
            report_template_slug=None,
        )
    assert caught.value.error_code is OnyxErrorCode.INVALID_INPUT
    db_session.rollback()


def test_scenario_publish_rewrites_conditional_slugs_to_ids(
    db_session: Session, catalog_skill: SystemSkill, catalog_user: User, unique_slug: str
) -> None:
    extra = create_system_skill(
        db_session,
        slug=f"{unique_slug}-extra",
        name=f"{unique_slug}-extra",
        description="Conditional skill.",
        category=SystemCatalogCategory.OFFICE,
        tags=[],
        built_in_skill_id=BUILT_IN_CONTENT_ID,
    )
    db_session.commit()
    entry = create_system_scenario(
        db_session,
        slug=f"{unique_slug}-cond",
        name="Conditional pack",
        description="Always one skill, optionally another.",
        category=SystemCatalogCategory.OFFICE,
        tags=[],
        rules={
            "objective": "Cover both the always-on and the conditional skill.",
            "conditional": [
                {
                    "if": {"intent": "deeper"},
                    "add_skill_slugs": [extra.slug],
                }
            ],
        },
        skill_slugs=[catalog_skill.slug],
        report_template_slug=None,
    )
    db_session.commit()
    try:
        always = publish_system_skill(
            db_session, catalog_skill, publisher=catalog_user
        )
        optional = publish_system_skill(db_session, extra, publisher=catalog_user)
        projection = publish_system_scenario(
            db_session, entry, publisher=catalog_user
        )
        db_session.commit()
        assert projection.rules["always_skill_ids"] == [str(always.id)]
        assert projection.rules["conditional"] == [
            {
                "if": {"intent": "deeper"},
                "add_skill_ids": [str(optional.id)],
            }
        ]
        assert "add_skill_slugs" not in projection.rules["conditional"][0]
    finally:
        db_session.execute(
            delete(Scenario).where(Scenario.system_scenario_id == entry.id)
        )
        db_session.execute(delete(SystemScenario).where(SystemScenario.id == entry.id))
        db_session.execute(delete(Skill).where(Skill.system_skill_id == extra.id))
        db_session.execute(delete(SystemSkill).where(SystemSkill.id == extra.id))
        db_session.commit()


def test_projection_lookup_ignores_user_forks(
    db_session: Session, catalog_skill: SystemSkill, catalog_user: User
) -> None:
    """A fork shares the catalog pointer, so only the owner column separates it."""
    projection = publish_system_skill(db_session, catalog_skill, publisher=catalog_user)
    db_session.commit()
    fork = fork_system_skill_for_user(db_session, catalog_skill, catalog_user)
    db_session.commit()

    found = find_projected_skill(db_session, catalog_skill)
    assert found is not None
    assert found.id == projection.id
    assert found.id != fork.id


def test_find_projected_report_template_returns_none_before_publish(
    db_session: Session, unique_slug: str
) -> None:
    entry = create_system_report_template(
        db_session,
        slug=unique_slug.replace("-", "_"),
        name="Unpublished template",
        description="Never published.",
        body="# Nothing\n",
        category=SystemCatalogCategory.GENERAL,
        tags=[],
    )
    db_session.commit()
    try:
        assert find_projected_report_template(db_session, entry) is None
    finally:
        db_session.execute(
            delete(SystemReportTemplate).where(SystemReportTemplate.id == entry.id)
        )
        db_session.commit()
