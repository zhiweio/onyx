"""Reconcile the shipped manifest into the system catalog.

Runs at startup and is idempotent. Rules that keep it safe to re-run:

- **Insert if absent.** An entry is matched by slug.
- **Refresh unedited BUILTIN rows.** A shipped row that an admin has never
  published or patched (``published_by_user_id is None`` and changelog still
  ``Shipped with Onyx.``) is updated when the manifest or official Word
  asset changes. Republish only when content actually changed, so versions
  do not bump on every boot.
- **Never overwrite admin work.** A row an admin published or patched is
  left alone.
- **Adopt before creating.** Earlier releases seeded workspace-owned rows
  directly into ``skill`` / ``scenario`` / ``report_template``. The sync links
  those rows to their catalog entry instead of publishing a duplicate beside
  them.
- **Retire removed builtins.** A shipped slug that left the manifest is
  unpublished (archived) so it leaves the user gallery. Scenarios go first,
  then templates, then skills, so skill unpublish is not blocked by a
  removed pack. If a live projection is still referenced, the catalog row
  is archived and kept.
"""

from __future__ import annotations

import datetime
import hashlib
from collections.abc import Callable
from functools import partial
from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from onyx.db.enums import (
    ReportTemplateKind,
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
from onyx.db.system_catalog.publish import (
    publish_system_report_template,
    publish_system_scenario,
    publish_system_skill,
    unpublish_system_report_template,
    unpublish_system_scenario,
    unpublish_system_skill,
)
from onyx.db.system_catalog.constants import normalize_tags
from onyx.db.system_catalog.report_template import (
    attach_catalog_docx_asset,
    create_system_report_template,
    get_system_report_template_by_slug,
    update_system_report_template,
)
from onyx.db.system_catalog.scenario import (
    create_system_scenario,
    get_system_scenario_by_slug,
    normalize_skill_slugs,
    update_system_scenario,
)
from onyx.db.system_catalog.skill import (
    create_system_skill,
    get_system_skill_by_slug,
    update_system_skill,
)
from onyx.error_handling.exceptions import OnyxError
from onyx.system_catalog.builtin.manifest import (
    BUILT_IN_REPORT_TEMPLATE_ENTRIES,
    BUILT_IN_SCENARIO_ENTRIES,
    BUILT_IN_SKILL_ENTRIES,
    BuiltInReportTemplateEntry,
    BuiltInScenarioEntry,
    BuiltInSkillEntry,
)
from onyx.system_catalog.builtin.word.generate import (
    generate_official_docx,
    official_builder_slugs,
)
from onyx.utils.logger import setup_logger

logger = setup_logger()

SHIPPED_CHANGELOG = "Shipped with Onyx."
_PATCH_GRACE = datetime.timedelta(seconds=2)
_CatalogRow = TypeVar(
    "_CatalogRow", SystemSkill, SystemScenario, SystemReportTemplate
)


def sync_builtin_system_catalog(db_session: Session) -> None:
    """Bring the catalog in line with the shipped manifest.

    Order matters: scenarios reference skills and report templates by slug, so
    both must be published before a scenario can resolve them. Each phase
    commits on its own, so a later phase cannot discard earlier work.
    """
    _sync_skills(db_session)
    db_session.commit()
    _sync_report_templates(db_session)
    db_session.commit()
    _sync_scenarios(db_session)
    db_session.commit()
    _retire_removed_builtins(db_session)
    db_session.commit()


def _publish_isolated(
    db_session: Session,
    slug: str,
    publish: Callable[[], object],
) -> None:
    """Publish one entry inside a savepoint, skipping it if it cannot publish.

    This runs during startup. A single unpublishable entry — a slug an end user
    already holds, or a pack whose skills a deployment removed — must not abort
    the boot, and must not discard the entries already reconciled.
    """
    savepoint = db_session.begin_nested()
    try:
        publish()
        savepoint.commit()
    except OnyxError:
        savepoint.rollback()
        logger.warning(
            "Skipping built-in catalog entry '%s': it could not be published "
            "in this deployment",
            slug,
            exc_info=True,
        )


def _retire_removed_builtins(db_session: Session) -> None:
    """Drop shipped catalog rows whose slugs left the manifest.

    Scenarios first, then templates, then skills. A removed pack must be gone
    before its skills can unpublish.
    """
    _retire_kind(
        db_session,
        rows=list(
            db_session.scalars(
                select(SystemScenario).where(
                    SystemScenario.origin == SystemCatalogOrigin.BUILTIN
                )
            )
        ),
        keep_slugs={entry.slug for entry in BUILT_IN_SCENARIO_ENTRIES},
        unpublish=unpublish_system_scenario,
    )
    _retire_kind(
        db_session,
        rows=list(
            db_session.scalars(
                select(SystemReportTemplate).where(
                    SystemReportTemplate.origin == SystemCatalogOrigin.BUILTIN
                )
            )
        ),
        keep_slugs={entry.slug for entry in BUILT_IN_REPORT_TEMPLATE_ENTRIES},
        unpublish=unpublish_system_report_template,
    )
    _retire_kind(
        db_session,
        rows=list(
            db_session.scalars(
                select(SystemSkill).where(
                    SystemSkill.origin == SystemCatalogOrigin.BUILTIN
                )
            )
        ),
        keep_slugs={entry.slug for entry in BUILT_IN_SKILL_ENTRIES},
        unpublish=unpublish_system_skill,
    )


def _retire_kind(
    db_session: Session,
    *,
    rows: list[_CatalogRow],
    keep_slugs: set[str],
    unpublish: Callable[[Session, _CatalogRow], None],
) -> None:
    for entry in rows:
        if entry.slug in keep_slugs:
            continue
        if entry.publish_status is SystemCatalogPublishStatus.ARCHIVED:
            continue
        if entry.publish_status is SystemCatalogPublishStatus.PUBLISHED:
            savepoint = db_session.begin_nested()
            try:
                unpublish(db_session, entry)
                savepoint.commit()
                continue
            except OnyxError:
                savepoint.rollback()
                logger.warning(
                    "Archiving built-in catalog entry '%s': it could not be "
                    "unpublished in this deployment",
                    entry.slug,
                    exc_info=True,
                )
        entry.publish_status = SystemCatalogPublishStatus.ARCHIVED
        db_session.flush()


def _is_unedited_builtin(
    entry: SystemSkill | SystemScenario | SystemReportTemplate,
) -> bool:
    """True when sync is still allowed to refresh this shipped row."""
    if entry.origin is not SystemCatalogOrigin.BUILTIN:
        return False
    if entry.published_by_user_id is not None:
        return False
    if entry.changelog not in ("", SHIPPED_CHANGELOG):
        return False
    if (
        entry.published_at is not None
        and entry.updated_at is not None
        and entry.updated_at > entry.published_at + _PATCH_GRACE
    ):
        return False
    return True


def _sync_skills(db_session: Session) -> None:
    for entry in BUILT_IN_SKILL_ENTRIES:
        catalog_entry = get_system_skill_by_slug(db_session, entry.slug)
        if catalog_entry is None:
            catalog_entry = create_system_skill(
                db_session,
                slug=entry.slug,
                name=entry.name,
                description=entry.description,
                category=entry.category,
                tags=list(entry.tags),
                built_in_skill_id=entry.built_in_skill_id,
                origin=SystemCatalogOrigin.BUILTIN,
            )
            _adopt_legacy_skill_row(db_session, catalog_entry)

        if (
            catalog_entry.publish_status is not SystemCatalogPublishStatus.DRAFT
            and not _is_unedited_builtin(catalog_entry)
        ):
            continue

        if not _skill_needs_refresh(catalog_entry, entry):
            continue

        update_system_skill(
            db_session,
            catalog_entry,
            name=entry.name,
            description=entry.description,
            category=entry.category,
            tags=list(entry.tags),
        )
        _publish_isolated(
            db_session,
            entry.slug,
            partial(
                publish_system_skill,
                db_session,
                catalog_entry,
                publisher=None,
                changelog=SHIPPED_CHANGELOG,
            ),
        )


def _skill_needs_refresh(
    catalog_entry: SystemSkill, entry: BuiltInSkillEntry
) -> bool:
    if catalog_entry.publish_status is SystemCatalogPublishStatus.DRAFT:
        return True
    if catalog_entry.name != entry.name:
        return True
    if catalog_entry.description != entry.description:
        return True
    if catalog_entry.category != entry.category:
        return True
    if list(catalog_entry.tags) != normalize_tags(list(entry.tags)):
        return True
    return False


def _adopt_legacy_skill_row(db_session: Session, entry: SystemSkill) -> None:
    """Claim a workspace skill an older migration seeded for this built-in.

    Without this the publish step would add a second row with the same name,
    and two enabled skills sharing a name break the sandbox fileset.
    """
    legacy = db_session.scalar(
        select(Skill).where(
            Skill.built_in_skill_id == entry.built_in_skill_id,
            Skill.author_user_id.is_(None),
            Skill.system_skill_id.is_(None),
        )
    )
    if legacy is None:
        return
    legacy.system_skill_id = entry.id
    db_session.flush()


def _sync_report_templates(db_session: Session) -> None:
    for entry in BUILT_IN_REPORT_TEMPLATE_ENTRIES:
        catalog_entry = get_system_report_template_by_slug(db_session, entry.slug)
        if catalog_entry is None:
            catalog_entry = create_system_report_template(
                db_session,
                slug=entry.slug,
                name=entry.name,
                description=entry.description,
                body=entry.read_body(),
                category=entry.category,
                tags=list(entry.tags),
                origin=SystemCatalogOrigin.BUILTIN,
            )
            _adopt_legacy_report_template_row(db_session, catalog_entry)

        if (
            catalog_entry.publish_status is not SystemCatalogPublishStatus.DRAFT
            and not _is_unedited_builtin(catalog_entry)
        ):
            continue

        if not _report_template_needs_refresh(catalog_entry, entry):
            continue

        _apply_report_template_manifest(db_session, catalog_entry, entry)
        _publish_isolated(
            db_session,
            entry.slug,
            partial(
                publish_system_report_template,
                db_session,
                catalog_entry,
                publisher=None,
                changelog=SHIPPED_CHANGELOG,
            ),
        )


def _report_template_needs_refresh(
    catalog_entry: SystemReportTemplate, entry: BuiltInReportTemplateEntry
) -> bool:
    if catalog_entry.publish_status is SystemCatalogPublishStatus.DRAFT:
        return True
    if catalog_entry.name != entry.name:
        return True
    if catalog_entry.description != entry.description:
        return True
    if catalog_entry.body != entry.read_body():
        return True
    if catalog_entry.category != entry.category:
        return True
    if list(catalog_entry.tags) != normalize_tags(list(entry.tags)):
        return True
    if entry.kind is ReportTemplateKind.DOCX:
        if catalog_entry.kind is not ReportTemplateKind.DOCX:
            return True
        if catalog_entry.asset_file_id is None:
            return True
        builder = entry.builder_slug()
        if builder in official_builder_slugs():
            expected = hashlib.sha256(generate_official_docx(builder)).hexdigest()
            if catalog_entry.asset_sha256 != expected:
                return True
    return False


def _apply_report_template_manifest(
    db_session: Session,
    catalog_entry: SystemReportTemplate,
    entry: BuiltInReportTemplateEntry,
) -> None:
    update_system_report_template(
        db_session,
        catalog_entry,
        name=entry.name,
        description=entry.description,
        body=entry.read_body(),
        category=entry.category,
        tags=list(entry.tags),
    )
    if entry.kind is not ReportTemplateKind.DOCX:
        return
    if entry.builder_slug() not in official_builder_slugs():
        return
    attach_catalog_docx_asset(
        db_session,
        catalog_entry,
        asset_bytes=generate_official_docx(entry.builder_slug()),
        filename=f"{entry.slug}.docx",
    )


def _adopt_legacy_report_template_row(
    db_session: Session, entry: SystemReportTemplate
) -> None:
    """Claim the workspace template on this slug.

    ``report_template.slug`` is globally unique, so without adoption publishing
    would fail outright on the duplicate.
    """
    legacy = db_session.scalar(
        select(ReportTemplate).where(
            ReportTemplate.slug == entry.slug,
            ReportTemplate.author_user_id.is_(None),
            ReportTemplate.system_report_template_id.is_(None),
        )
    )
    if legacy is None:
        return
    legacy.system_report_template_id = entry.id
    db_session.flush()


def _sync_scenarios(db_session: Session) -> None:
    for entry in BUILT_IN_SCENARIO_ENTRIES:
        catalog_entry = get_system_scenario_by_slug(db_session, entry.slug)
        if catalog_entry is None:
            catalog_entry = create_system_scenario(
                db_session,
                slug=entry.slug,
                name=entry.name,
                description=entry.description,
                category=entry.category,
                tags=list(entry.tags),
                rules=entry.read_rules(),
                skill_slugs=list(entry.skill_slugs),
                report_template_slug=entry.report_template_slug,
                origin=SystemCatalogOrigin.BUILTIN,
            )
            _adopt_legacy_scenario_row(db_session, catalog_entry, entry)

        if (
            catalog_entry.publish_status is not SystemCatalogPublishStatus.DRAFT
            and not _is_unedited_builtin(catalog_entry)
        ):
            continue

        if not _scenario_needs_refresh(catalog_entry, entry):
            continue

        update_system_scenario(
            db_session,
            catalog_entry,
            name=entry.name,
            description=entry.description,
            category=entry.category,
            tags=list(entry.tags),
            rules=entry.read_rules(),
            skill_slugs=list(entry.skill_slugs),
            report_template_slug=entry.report_template_slug,
            clear_report_template=entry.report_template_slug is None,
        )
        _publish_isolated(
            db_session,
            entry.slug,
            partial(
                publish_system_scenario,
                db_session,
                catalog_entry,
                publisher=None,
                changelog=SHIPPED_CHANGELOG,
            ),
        )


def _scenario_needs_refresh(
    catalog_entry: SystemScenario, entry: BuiltInScenarioEntry
) -> bool:
    if catalog_entry.publish_status is SystemCatalogPublishStatus.DRAFT:
        return True
    return (
        catalog_entry.name != entry.name
        or catalog_entry.description != entry.description
        or catalog_entry.category != entry.category
        or list(catalog_entry.tags) != normalize_tags(list(entry.tags))
        or list(catalog_entry.skill_slugs) != normalize_skill_slugs(list(entry.skill_slugs))
        or catalog_entry.report_template_slug != entry.report_template_slug
        or dict(catalog_entry.rules or {}) != entry.read_rules()
    )


def _adopt_legacy_scenario_row(
    db_session: Session, entry: SystemScenario, manifest_entry: BuiltInScenarioEntry
) -> None:
    """Claim a workspace pack an older migration seeded under this name.

    Scenarios have no slug in the runtime table, so the manifest names the
    legacy row explicitly rather than guessing.
    """
    if manifest_entry.adopt_runtime_name is None:
        return
    legacy = db_session.scalar(
        select(Scenario).where(
            Scenario.name == manifest_entry.adopt_runtime_name,
            Scenario.author_user_id.is_(None),
            Scenario.system_scenario_id.is_(None),
        )
    )
    if legacy is None:
        return
    legacy.system_scenario_id = entry.id
    db_session.flush()
