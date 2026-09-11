"""The shipped manifest and the sync that reconciles it into the catalog.

The sync runs on every boot, so the properties that matter are: it is
idempotent, it adopts rows earlier releases seeded instead of duplicating them,
and it never overwrites an admin's edits to shipped content.
"""

from __future__ import annotations

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from onyx.db.enums import (
    SystemCatalogCategory,
    SystemCatalogOrigin,
    SystemCatalogPublishStatus,
)
from onyx.db.models import (
    ReportTemplate,
    Scenario,
    Skill,
    SystemReportTemplate,
    SystemScenario,
    SystemSkill,
)
from onyx.db.system_catalog.publish import find_projected_skill
from onyx.db.system_catalog.report_template import (
    get_system_report_template_by_slug,
)
from onyx.db.system_catalog.skill import create_system_skill, get_system_skill_by_slug
from onyx.skills.built_in import BUILT_IN_SKILLS
from onyx.skills.metadata import parse_skill_document
from onyx.system_catalog.builtin.manifest import (
    BUILT_IN_REPORT_TEMPLATE_ENTRIES,
    BUILT_IN_SCENARIO_ENTRIES,
    BUILT_IN_SKILL_ENTRIES,
)
from onyx.system_catalog.builtin.sync import sync_builtin_system_catalog
from tests.external_dependency_unit.conftest import create_test_user

# A slug this change introduces, so no prior migration seeded it and a user
# could plausibly already hold it.
COLLIDABLE_SLUG = "initiation_report"

# ── manifest integrity (no database needed) ─────────────────────────────────


def test_every_manifest_skill_points_at_real_built_in_content() -> None:
    missing = [
        entry.slug
        for entry in BUILT_IN_SKILL_ENTRIES
        if entry.built_in_skill_id not in BUILT_IN_SKILLS
    ]
    assert missing == []


def test_every_built_in_skill_document_parses() -> None:
    """The registry parses at import; assert it explicitly for the new content."""
    for entry in BUILT_IN_SKILL_ENTRIES:
        definition = BUILT_IN_SKILLS[entry.built_in_skill_id]
        source_name = "SKILL.md.template" if definition.has_template else "SKILL.md"
        document = parse_skill_document(
            (definition.source_dir / source_name).read_bytes(),
            directory_name=entry.built_in_skill_id,
        )
        assert document.metadata.name == entry.built_in_skill_id


def test_manifest_slugs_are_unique_within_each_kind() -> None:
    for entries in (
        BUILT_IN_SKILL_ENTRIES,
        BUILT_IN_REPORT_TEMPLATE_ENTRIES,
        BUILT_IN_SCENARIO_ENTRIES,
    ):
        slugs = [entry.slug for entry in entries]
        assert len(slugs) == len(set(slugs))


def test_every_manifest_report_template_body_exists() -> None:
    for entry in BUILT_IN_REPORT_TEMPLATE_ENTRIES:
        assert entry.read_body().strip()


def test_every_manifest_scenario_playbook_exists() -> None:
    for entry in BUILT_IN_SCENARIO_ENTRIES:
        rules = entry.read_rules()
        assert rules.get("objective")
        assert rules.get("phases")


def test_every_official_template_has_a_word_builder() -> None:
    from onyx.system_catalog.builtin.word.generate import official_builder_slugs

    builders = official_builder_slugs()
    missing = [
        entry.slug
        for entry in BUILT_IN_REPORT_TEMPLATE_ENTRIES
        if entry.builder_slug() not in builders
    ]
    assert missing == []


def test_scenarios_only_reference_declared_skills_and_templates() -> None:
    skill_slugs = {entry.slug for entry in BUILT_IN_SKILL_ENTRIES}
    template_slugs = {entry.slug for entry in BUILT_IN_REPORT_TEMPLATE_ENTRIES}
    for scenario in BUILT_IN_SCENARIO_ENTRIES:
        assert set(scenario.skill_slugs) <= skill_slugs, scenario.slug
        if scenario.report_template_slug is not None:
            assert scenario.report_template_slug in template_slugs, scenario.slug


# ── sync behavior ───────────────────────────────────────────────────────────


@pytest.fixture
def synced(db_session: Session) -> None:
    sync_builtin_system_catalog(db_session)


def _counts(db_session: Session) -> dict[str, int]:
    return {
        "catalog_skill": _count(db_session, SystemSkill),
        "catalog_scenario": _count(db_session, SystemScenario),
        "catalog_report_template": _count(db_session, SystemReportTemplate),
        "workspace_skill": _count_workspace(db_session, Skill),
        "workspace_scenario": _count_workspace(db_session, Scenario),
        "workspace_report_template": _count_workspace(db_session, ReportTemplate),
    }


def _count(db_session: Session, model: type) -> int:
    return int(db_session.scalar(select(func.count()).select_from(model)) or 0)


def _count_workspace(db_session: Session, model: type) -> int:
    return int(
        db_session.scalar(
            select(func.count())
            .select_from(model)
            .where(model.author_user_id.is_(None))
        )
        or 0
    )


@pytest.mark.usefixtures("synced")
def test_sync_publishes_every_manifest_entry(db_session: Session) -> None:
    for entry in BUILT_IN_SKILL_ENTRIES:
        catalog_entry = get_system_skill_by_slug(db_session, entry.slug)
        assert catalog_entry is not None, entry.slug
        assert catalog_entry.origin is SystemCatalogOrigin.BUILTIN
        assert catalog_entry.publish_status is SystemCatalogPublishStatus.PUBLISHED, (
            entry.slug
        )
        assert find_projected_skill(db_session, catalog_entry) is not None


@pytest.mark.usefixtures("synced")
def test_sync_is_idempotent(db_session: Session) -> None:
    before = _counts(db_session)
    versions_before = _skill_versions(db_session)
    template_versions_before = _template_versions(db_session)

    sync_builtin_system_catalog(db_session)
    sync_builtin_system_catalog(db_session)

    assert _counts(db_session) == before
    # Re-running must not republish, which would bump versions and falsely tell
    # every user their copy is out of date.
    assert _skill_versions(db_session) == versions_before
    assert _template_versions(db_session) == template_versions_before


def _skill_versions(db_session: Session) -> dict[str, int]:
    rows = db_session.execute(select(SystemSkill.slug, SystemSkill.version)).all()
    return {slug: version for slug, version in rows}


def _template_versions(db_session: Session) -> dict[str, int]:
    rows = db_session.execute(
        select(SystemReportTemplate.slug, SystemReportTemplate.version)
    ).all()
    return {slug: version for slug, version in rows}


@pytest.mark.usefixtures("synced")
def test_sync_does_not_duplicate_workspace_skill_names(db_session: Session) -> None:
    """Two enabled skills sharing a name break the sandbox fileset assembler."""
    duplicates = db_session.execute(
        select(Skill.name)
        .where(Skill.author_user_id.is_(None))
        .group_by(Skill.name)
        .having(func.count() > 1)
    ).all()
    assert duplicates == []


@pytest.mark.usefixtures("synced")
def test_sync_adopts_rows_seeded_by_earlier_releases(db_session: Session) -> None:
    """Content shipped by migrations must end up linked, not shadowed."""
    for entry in BUILT_IN_SKILL_ENTRIES:
        matching = db_session.scalars(
            select(Skill).where(
                Skill.built_in_skill_id == entry.built_in_skill_id,
                Skill.author_user_id.is_(None),
            )
        ).all()
        assert len(matching) == 1, entry.slug
        assert matching[0].system_skill_id is not None, entry.slug


@pytest.mark.usefixtures("synced")
def test_sync_skips_an_entry_whose_slug_a_user_already_holds(
    db_session: Session,
) -> None:
    """A slug collision must not abort startup.

    ``sync_builtin_system_catalog`` runs inside the FastAPI lifespan, so an
    unhandled error there is a permanent boot failure.
    """
    sync_builtin_system_catalog(db_session)
    entry = get_system_report_template_by_slug(db_session, COLLIDABLE_SLUG)
    assert entry is not None

    user = create_test_user(db_session, "slug_squatter")
    squatter = ReportTemplate(
        slug=COLLIDABLE_SLUG,
        name="A user's own template",
        description="",
        body="# Mine\n",
        author_user_id=user.id,
        is_builtin=False,
    )
    try:
        # Take the slug away from the catalog and hand it to a user.
        db_session.execute(
            delete(ReportTemplate).where(
                ReportTemplate.system_report_template_id == entry.id
            )
        )
        entry.publish_status = SystemCatalogPublishStatus.DRAFT
        db_session.add(squatter)
        db_session.commit()

        # Must not raise.
        sync_builtin_system_catalog(db_session)

        db_session.refresh(entry)
        assert entry.publish_status is SystemCatalogPublishStatus.DRAFT
        # Every other entry still reconciles.
        other = get_system_report_template_by_slug(db_session, _another_template_slug())
        assert other is not None
        assert other.publish_status is SystemCatalogPublishStatus.PUBLISHED
    finally:
        db_session.delete(squatter)
        db_session.commit()
        sync_builtin_system_catalog(db_session)


def _another_template_slug() -> str:
    return next(
        entry.slug
        for entry in BUILT_IN_REPORT_TEMPLATE_ENTRIES
        if entry.slug != COLLIDABLE_SLUG
    )


@pytest.mark.usefixtures("synced")
def test_sync_preserves_admin_edits_to_shipped_content(
    db_session: Session,
) -> None:
    entry = get_system_skill_by_slug(db_session, BUILT_IN_SKILL_ENTRIES[0].slug)
    assert entry is not None
    original_description = entry.description
    try:
        entry.description = "Edited by an admin."
        db_session.commit()

        sync_builtin_system_catalog(db_session)
        db_session.refresh(entry)

        assert entry.description == "Edited by an admin."
    finally:
        entry.description = original_description
        db_session.commit()


@pytest.mark.usefixtures("synced")
def test_sync_attaches_official_word_assets(db_session: Session) -> None:
    from onyx.db.enums import ReportTemplateKind
    from onyx.report_templates.placeholders import (
        normalize_placeholder_schema,
        placeholder_names,
    )

    entry = get_system_report_template_by_slug(db_session, "initiation_report")
    assert entry is not None
    assert entry.kind is ReportTemplateKind.DOCX
    assert entry.asset_file_id is not None
    names = placeholder_names(normalize_placeholder_schema(entry.placeholders))
    assert "entity_name" in names


@pytest.mark.usefixtures("synced")
def test_sync_does_not_overwrite_an_admin_published_template(
    db_session: Session,
) -> None:
    entry = get_system_report_template_by_slug(db_session, "initiation_report")
    assert entry is not None
    user = create_test_user(db_session, "tpl_editor")
    original_body = entry.body
    try:
        entry.body = "# Edited by an admin.\n"
        entry.published_by_user_id = user.id
        entry.changelog = "Admin rewrite"
        db_session.commit()

        sync_builtin_system_catalog(db_session)
        db_session.refresh(entry)

        assert entry.body == "# Edited by an admin.\n"
    finally:
        entry.body = original_body
        entry.published_by_user_id = None
        entry.changelog = "Shipped with Onyx."
        db_session.commit()


@pytest.mark.usefixtures("synced")
def test_sync_retires_builtins_removed_from_the_manifest(
    db_session: Session,
) -> None:
    leftover = create_system_skill(
        db_session,
        slug="retired-catalog-skill",
        name="retired-catalog-skill",
        description="Removed from the manifest.",
        category=SystemCatalogCategory.OFFICE,
        tags=[],
        built_in_skill_id="retired-catalog-skill",
        origin=SystemCatalogOrigin.BUILTIN,
    )
    leftover.publish_status = SystemCatalogPublishStatus.PUBLISHED
    leftover.changelog = "Shipped with Onyx."
    db_session.commit()

    try:
        sync_builtin_system_catalog(db_session)

        retired = get_system_skill_by_slug(db_session, "retired-catalog-skill")
        assert retired is not None
        assert retired.publish_status is SystemCatalogPublishStatus.ARCHIVED
        assert find_projected_skill(db_session, retired) is None
    finally:
        leftover = get_system_skill_by_slug(db_session, "retired-catalog-skill")
        if leftover is not None:
            db_session.delete(leftover)
            db_session.commit()
