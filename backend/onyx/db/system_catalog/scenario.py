"""CRUD and search for ``system_scenario`` catalog entries."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from onyx.db.enums import (
    SystemCatalogCategory,
    SystemCatalogOrigin,
    SystemCatalogPublishStatus,
)
from onyx.db.models import SystemScenario
from onyx.db.system_catalog.constants import (
    DESCRIPTION_MAX,
    NAME_MAX,
    apply_tag_filter,
    apply_text_search,
    normalize_catalog_slug,
    normalize_report_template_catalog_slug,
    normalize_required_text,
    normalize_tags,
)
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError

SKILL_SLUGS_MAX_COUNT = 50


def normalize_skill_slugs(raw: list[str]) -> list[str]:
    """Normalize bound skill slugs, keeping author order and dropping repeats.

    Order matters: it becomes ``scenario__skill.sort_order`` on publish, which
    drives the order skills appear in the rendered SCENARIO.md.
    """
    normalized: list[str] = []
    seen: set[str] = set()
    for slug in raw:
        candidate = normalize_catalog_slug(slug)
        if candidate in seen:
            continue
        seen.add(candidate)
        normalized.append(candidate)
    if len(normalized) > SKILL_SLUGS_MAX_COUNT:
        raise OnyxError(
            OnyxErrorCode.INVALID_INPUT,
            f"At most {SKILL_SLUGS_MAX_COUNT} skills can be bound to a scenario",
        )
    return normalized


def list_system_scenarios(
    db_session: Session,
    *,
    query: str | None = None,
    category: SystemCatalogCategory | None = None,
    tags: list[str] | None = None,
    statuses: list[SystemCatalogPublishStatus] | None = None,
) -> list[SystemScenario]:
    stmt = select(SystemScenario)
    if statuses:
        stmt = stmt.where(SystemScenario.publish_status.in_(statuses))
    if category is not None:
        stmt = stmt.where(SystemScenario.category == category)
    stmt = apply_text_search(stmt, SystemScenario, query)
    stmt = apply_tag_filter(stmt, SystemScenario, tags)
    stmt = stmt.order_by(SystemScenario.category.asc(), SystemScenario.name.asc())
    return list(db_session.scalars(stmt).all())


def get_system_scenario(db_session: Session, entry_id: UUID) -> SystemScenario:
    entry = db_session.get(SystemScenario, entry_id)
    if entry is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Catalog scenario not found")
    return entry


def get_system_scenario_by_slug(
    db_session: Session, slug: str
) -> SystemScenario | None:
    return db_session.scalar(select(SystemScenario).where(SystemScenario.slug == slug))


def create_system_scenario(
    db_session: Session,
    *,
    slug: str,
    name: str,
    description: str,
    category: SystemCatalogCategory,
    tags: list[str],
    rules: dict[str, Any],
    skill_slugs: list[str],
    report_template_slug: str | None,
    origin: SystemCatalogOrigin = SystemCatalogOrigin.ADMIN,
) -> SystemScenario:
    entry = SystemScenario(
        slug=normalize_catalog_slug(slug),
        name=normalize_required_text(name, field="Name", max_length=NAME_MAX),
        description=normalize_required_text(
            description, field="Description", max_length=DESCRIPTION_MAX
        ),
        category=category,
        tags=normalize_tags(tags),
        publish_status=SystemCatalogPublishStatus.DRAFT,
        version=0,
        changelog="",
        origin=origin,
        rules=dict(rules),
        skill_slugs=normalize_skill_slugs(skill_slugs),
        report_template_slug=(
            normalize_report_template_catalog_slug(report_template_slug)
            if report_template_slug
            else None
        ),
    )
    db_session.add(entry)
    try:
        db_session.flush()
    except IntegrityError as exc:
        db_session.rollback()
        raise OnyxError(
            OnyxErrorCode.DUPLICATE_RESOURCE, "Catalog slug already exists"
        ) from exc
    return entry


def update_system_scenario(
    db_session: Session,
    entry: SystemScenario,
    *,
    name: str | None = None,
    description: str | None = None,
    category: SystemCatalogCategory | None = None,
    tags: list[str] | None = None,
    rules: dict[str, Any] | None = None,
    skill_slugs: list[str] | None = None,
    report_template_slug: str | None = None,
    clear_report_template: bool = False,
) -> SystemScenario:
    if name is not None:
        entry.name = normalize_required_text(name, field="Name", max_length=NAME_MAX)
    if description is not None:
        entry.description = normalize_required_text(
            description, field="Description", max_length=DESCRIPTION_MAX
        )
    if category is not None:
        entry.category = category
    if tags is not None:
        entry.tags = normalize_tags(tags)
    if rules is not None:
        entry.rules = dict(rules)
    if skill_slugs is not None:
        entry.skill_slugs = normalize_skill_slugs(skill_slugs)
    if clear_report_template:
        entry.report_template_slug = None
    elif report_template_slug is not None:
        entry.report_template_slug = normalize_report_template_catalog_slug(
            report_template_slug
        )
    db_session.flush()
    return entry


def delete_system_scenario(db_session: Session, entry: SystemScenario) -> None:
    db_session.delete(entry)
    db_session.flush()
