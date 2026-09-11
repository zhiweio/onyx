"""Publish a catalog entry into the runtime tables, and take it back down.

Publishing is a projection, not a new runtime concept: it upserts a
workspace-owned row (``author_user_id IS NULL``, ``public_permission=VIEWER``)
in ``skill`` / ``scenario`` / ``report_template``. Every existing consumer —
the sandbox skill push, the SCENARIO.md renderer, the report template lookup —
keeps reading the runtime tables and needs no change.

Identity: a projection is the row whose ``system_<kind>_id`` matches the entry
and whose ``author_user_id`` is NULL. User forks share the same pointer but
carry an owner, which is what keeps them out of the projection lookup.
"""

from __future__ import annotations

import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from onyx.db.enums import (
    ReportTemplateKind,
    ScenarioSharePermission,
    SkillSharePermission,
    SystemCatalogPublishStatus,
)
from onyx.db.models import (
    ReportTemplate,
    Scenario,
    Scenario__Skill,
    Skill,
    SystemReportTemplate,
    SystemScenario,
    SystemSkill,
    User,
)
from onyx.db.report_template import count_report_template_references
from onyx.db.system_catalog.constants import CHANGELOG_MAX, normalize_optional_text
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError


def find_projected_skill(db_session: Session, entry: SystemSkill) -> Skill | None:
    return db_session.scalar(
        select(Skill).where(
            Skill.system_skill_id == entry.id,
            Skill.author_user_id.is_(None),
        )
    )


def find_projected_scenario(
    db_session: Session, entry: SystemScenario
) -> Scenario | None:
    return db_session.scalar(
        select(Scenario).where(
            Scenario.system_scenario_id == entry.id,
            Scenario.author_user_id.is_(None),
        )
    )


def find_projected_report_template(
    db_session: Session, entry: SystemReportTemplate
) -> ReportTemplate | None:
    return db_session.scalar(
        select(ReportTemplate).where(
            ReportTemplate.system_report_template_id == entry.id,
            ReportTemplate.author_user_id.is_(None),
        )
    )


def _mark_published(
    entry: SystemSkill | SystemScenario | SystemReportTemplate,
    *,
    publisher: User | None,
    changelog: str,
) -> None:
    entry.publish_status = SystemCatalogPublishStatus.PUBLISHED
    entry.version += 1
    entry.changelog = normalize_optional_text(
        changelog, field="Changelog", max_length=CHANGELOG_MAX
    )
    entry.published_at = datetime.datetime.now(datetime.timezone.utc)
    # None when the shipped-content sync publishes, which has no acting user.
    entry.published_by_user_id = publisher.id if publisher is not None else None


def publish_system_skill(
    db_session: Session,
    entry: SystemSkill,
    *,
    publisher: User | None,
    changelog: str = "",
) -> Skill:
    """Create or refresh the workspace-owned ``skill`` row for this entry."""
    _mark_published(entry, publisher=publisher, changelog=changelog)

    projection = find_projected_skill(db_session, entry)
    if projection is None:
        projection = Skill(
            name=entry.slug,
            description=entry.description,
            built_in_skill_id=entry.built_in_skill_id,
            bundle_file_id=entry.bundle_file_id,
            bundle_sha256=entry.bundle_sha256,
            is_valid=True,
            author_user_id=None,
            public_permission=SkillSharePermission.VIEWER,
            system_skill_id=entry.id,
        )
        db_session.add(projection)
    else:
        projection.name = entry.slug
        projection.description = entry.description
        projection.built_in_skill_id = entry.built_in_skill_id
        projection.bundle_file_id = entry.bundle_file_id
        projection.bundle_sha256 = entry.bundle_sha256
        projection.is_valid = True
        projection.public_permission = SkillSharePermission.VIEWER
    projection.system_skill_version = entry.version
    db_session.flush()
    return projection


def publish_system_report_template(
    db_session: Session,
    entry: SystemReportTemplate,
    *,
    publisher: User | None,
    changelog: str = "",
) -> ReportTemplate:
    _mark_published(entry, publisher=publisher, changelog=changelog)

    projection = find_projected_report_template(db_session, entry)
    if projection is None:
        # report_template.slug is globally unique and is the key scenarios
        # reference, so a pre-existing row on this slug is a real conflict the
        # admin has to resolve rather than something to silently take over.
        conflicting = db_session.scalar(
            select(ReportTemplate).where(ReportTemplate.slug == entry.slug)
        )
        if conflicting is not None:
            raise OnyxError(
                OnyxErrorCode.DUPLICATE_RESOURCE,
                f"A report template already uses the ID '{entry.slug}'",
            )
        projection = ReportTemplate(
            slug=entry.slug,
            name=entry.name,
            description=entry.description,
            body=entry.body,
            author_user_id=None,
            is_builtin=True,
            system_report_template_id=entry.id,
        )
        db_session.add(projection)
    else:
        projection.name = entry.name
        projection.description = entry.description
        projection.body = entry.body
    # The projection shares the catalog entry's blob rather than copying it:
    # the catalog row owns the asset and outlives the projection.
    projection.kind = entry.kind
    projection.asset_file_id = entry.asset_file_id
    projection.asset_sha256 = entry.asset_sha256
    projection.asset_filename = entry.asset_filename
    projection.placeholders = list(entry.placeholders)
    projection.system_report_template_version = entry.version
    db_session.flush()
    return projection


def publish_system_scenario(
    db_session: Session,
    entry: SystemScenario,
    *,
    publisher: User | None,
    changelog: str = "",
) -> Scenario:
    """Project the scenario, resolving each bound skill slug to its projection.

    A scenario can only bind skills that are themselves published, otherwise the
    pack would reference skills no user can see.
    """
    bound_skills = _resolve_bound_skills(db_session, entry)
    extra_conditional = _resolve_conditional_skills(db_session, entry, bound_skills)
    _assert_report_template_binding_is_shared(db_session, entry)
    bound_skills = _ensure_docx_skill_for_word_template(
        db_session, entry, bound_skills
    )
    _mark_published(entry, publisher=publisher, changelog=changelog)

    projection = find_projected_scenario(db_session, entry)
    if projection is None:
        projection = Scenario(
            name=entry.name,
            description=entry.description,
            author_user_id=None,
            public_permission=ScenarioSharePermission.VIEWER,
            rules={},
            system_scenario_id=entry.id,
        )
        db_session.add(projection)
        db_session.flush()
    else:
        projection.name = entry.name
        projection.description = entry.description
        projection.public_permission = ScenarioSharePermission.VIEWER
    projection.report_template = entry.report_template_slug
    projection.rules = _materialize_rules(entry, bound_skills, extra_conditional)
    projection.system_scenario_version = entry.version

    projection.skill_links.clear()
    db_session.flush()
    for sort_order, skill in enumerate(bound_skills):
        projection.skill_links.append(
            Scenario__Skill(
                scenario_id=projection.id,
                skill_id=skill.id,
                sort_order=sort_order,
            )
        )
    db_session.flush()
    return projection


def _resolve_bound_skills(db_session: Session, entry: SystemScenario) -> list[Skill]:
    resolved: list[Skill] = []
    missing: list[str] = []
    for slug in entry.skill_slugs:
        catalog_skill = db_session.scalar(
            select(SystemSkill).where(SystemSkill.slug == slug)
        )
        if (
            catalog_skill is None
            or catalog_skill.publish_status is not SystemCatalogPublishStatus.PUBLISHED
        ):
            missing.append(slug)
            continue
        projection = find_projected_skill(db_session, catalog_skill)
        if projection is None:
            missing.append(slug)
            continue
        resolved.append(projection)
    if missing:
        raise OnyxError(
            OnyxErrorCode.INVALID_INPUT,
            "Publish these skills first: " + ", ".join(sorted(missing)),
        )
    return resolved


def _ensure_docx_skill_for_word_template(
    db_session: Session,
    entry: SystemScenario,
    bound_skills: list[Skill],
) -> list[Skill]:
    """Auto-inject the ``docx`` skill when the bound template is a Word file.

    Catalog packs should list ``docx`` themselves. This is the safety net so a
    Word-bound pack never reaches a session without the filler skill.
    """
    if entry.report_template_slug is None:
        return bound_skills
    template = db_session.scalar(
        select(ReportTemplate).where(
            ReportTemplate.slug == entry.report_template_slug,
            ReportTemplate.author_user_id.is_(None),
        )
    )
    if template is None or template.kind is not ReportTemplateKind.DOCX:
        return bound_skills
    if any(
        skill.name == "docx" or skill.built_in_skill_id == "docx"
        for skill in bound_skills
    ):
        return bound_skills
    catalog_skill = db_session.scalar(
        select(SystemSkill).where(SystemSkill.slug == "docx")
    )
    if (
        catalog_skill is None
        or catalog_skill.publish_status is not SystemCatalogPublishStatus.PUBLISHED
    ):
        raise OnyxError(
            OnyxErrorCode.INVALID_INPUT,
            "Publish the 'docx' skill first — this pack binds a Word template",
        )
    projection = find_projected_skill(db_session, catalog_skill)
    if projection is None:
        raise OnyxError(
            OnyxErrorCode.INVALID_INPUT,
            "Publish the 'docx' skill first — this pack binds a Word template",
        )
    return [*bound_skills, projection]


def _assert_report_template_binding_is_shared(
    db_session: Session, entry: SystemScenario
) -> None:
    """Require the bound slug to resolve to a workspace-owned template.

    ``report_template.slug`` is globally unique and first-come-first-served, so
    an ordinary user can hold the slug an admin wants. Binding to that row would
    splice one user's private template into every other user's SCENARIO.md,
    because ``render_scenario_markdown_named`` resolves the slug globally.
    """
    if entry.report_template_slug is None:
        return
    template = db_session.scalar(
        select(ReportTemplate).where(
            ReportTemplate.slug == entry.report_template_slug,
            ReportTemplate.author_user_id.is_(None),
        )
    )
    if template is None:
        raise OnyxError(
            OnyxErrorCode.INVALID_INPUT,
            f"Publish the report template '{entry.report_template_slug}' first, "
            "or pick a different one — no shared template uses that ID",
        )


def _conditional_slugs_from_rules(rules: dict[str, object] | None) -> list[str]:
    slugs: list[str] = []
    if not rules:
        return slugs
    raw = rules.get("conditional")
    if not isinstance(raw, list):
        return slugs
    for item in raw:
        if not isinstance(item, dict):
            continue
        for slug in item.get("add_skill_slugs") or []:
            text = str(slug).strip()
            if text:
                slugs.append(text)
    return slugs


def _resolve_skills_for_slugs(
    db_session: Session, slugs: list[str]
) -> dict[str, Skill]:
    resolved: dict[str, Skill] = {}
    missing: list[str] = []
    for slug in slugs:
        catalog_skill = db_session.scalar(
            select(SystemSkill).where(SystemSkill.slug == slug)
        )
        if (
            catalog_skill is None
            or catalog_skill.publish_status is not SystemCatalogPublishStatus.PUBLISHED
        ):
            missing.append(slug)
            continue
        projection = find_projected_skill(db_session, catalog_skill)
        if projection is None:
            missing.append(slug)
            continue
        resolved[slug] = projection
    if missing:
        raise OnyxError(
            OnyxErrorCode.INVALID_INPUT,
            "Publish these skills first: " + ", ".join(sorted(set(missing))),
        )
    return resolved


def _resolve_conditional_skills(
    db_session: Session, entry: SystemScenario, bound_skills: list[Skill]
) -> dict[str, Skill]:
    bound_slugs = set(entry.skill_slugs)
    extra = [
        slug
        for slug in _conditional_slugs_from_rules(entry.rules)
        if slug not in bound_slugs
    ]
    if not extra:
        return {}
    return _resolve_skills_for_slugs(db_session, extra)


def _materialize_rules(
    entry: SystemScenario,
    bound_skills: list[Skill],
    extra_conditional: dict[str, Skill] | None = None,
) -> dict[str, object]:
    """Rewrite catalog rules into the runtime shape.

    The catalog stores slugs so the manifest stays portable; the runtime
    resolver (``resolve_scenario_skill_ids``) works on skill UUIDs.
    """
    rules = dict(entry.rules or {})
    rules["always_skill_ids"] = [str(skill.id) for skill in bound_skills]
    slug_to_id = {
        slug: str(skill.id) for slug, skill in zip(entry.skill_slugs, bound_skills)
    }
    if extra_conditional:
        for slug, skill in extra_conditional.items():
            slug_to_id[slug] = str(skill.id)
    raw_conditionals = rules.get("conditional")
    if isinstance(raw_conditionals, list):
        rewritten: list[dict[str, object]] = []
        for item in raw_conditionals:
            if not isinstance(item, dict):
                continue
            clone = dict(item)
            slugs = [str(slug).strip() for slug in (clone.get("add_skill_slugs") or [])]
            ids = [slug_to_id[slug] for slug in slugs if slug in slug_to_id]
            if ids:
                clone["add_skill_ids"] = ids
            clone.pop("add_skill_slugs", None)
            rewritten.append(clone)
        if rewritten:
            rules["conditional"] = rewritten
        else:
            rules.pop("conditional", None)
    return rules


def unpublish_system_skill(db_session: Session, entry: SystemSkill) -> None:
    """Archive the entry and drop its projection.

    User forks are untouched — they are separate rows with their own owner.
    """
    projection = find_projected_skill(db_session, entry)
    if projection is not None:
        _assert_skill_not_bound_to_published_scenario(db_session, entry)
        db_session.delete(projection)
    entry.publish_status = SystemCatalogPublishStatus.ARCHIVED
    db_session.flush()


def unpublish_system_scenario(db_session: Session, entry: SystemScenario) -> None:
    projection = find_projected_scenario(db_session, entry)
    if projection is not None:
        db_session.delete(projection)
    entry.publish_status = SystemCatalogPublishStatus.ARCHIVED
    db_session.flush()


def unpublish_system_report_template(
    db_session: Session, entry: SystemReportTemplate
) -> None:
    projection = find_projected_report_template(db_session, entry)
    if projection is not None:
        # Mirrors delete_report_template: scenarios reference templates by slug,
        # so dropping one in use would leave dangling packs.
        referenced = count_report_template_references(db_session, projection.slug)
        if referenced > 0:
            raise OnyxError(
                OnyxErrorCode.CONFLICT,
                "Scenarios still use this template",
                extra={"referenced_count": referenced},
            )
        db_session.delete(projection)
    entry.publish_status = SystemCatalogPublishStatus.ARCHIVED
    db_session.flush()


def _assert_skill_not_bound_to_published_scenario(
    db_session: Session, entry: SystemSkill
) -> None:
    bound = db_session.scalars(
        select(SystemScenario).where(
            SystemScenario.publish_status == SystemCatalogPublishStatus.PUBLISHED,
            SystemScenario.skill_slugs.contains([entry.slug]),
        )
    ).all()
    if bound:
        raise OnyxError(
            OnyxErrorCode.CONFLICT,
            "Published scenarios still use this skill: "
            + ", ".join(sorted(scenario.name for scenario in bound)),
            extra={"referenced_count": len(bound)},
        )
