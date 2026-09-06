"""CRUD and search for ``system_skill`` catalog entries."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from onyx.db.enums import (
    SystemCatalogCategory,
    SystemCatalogOrigin,
    SystemCatalogPublishStatus,
)
from onyx.db.models import SystemSkill
from onyx.db.system_catalog.constants import (
    DESCRIPTION_MAX,
    SKILL_NAME_MAX,
    apply_tag_filter,
    apply_text_search,
    normalize_catalog_slug,
    normalize_required_text,
    normalize_tags,
)
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError


def list_system_skills(
    db_session: Session,
    *,
    query: str | None = None,
    category: SystemCatalogCategory | None = None,
    tags: list[str] | None = None,
    statuses: list[SystemCatalogPublishStatus] | None = None,
) -> list[SystemSkill]:
    stmt = select(SystemSkill)
    if statuses:
        stmt = stmt.where(SystemSkill.publish_status.in_(statuses))
    if category is not None:
        stmt = stmt.where(SystemSkill.category == category)
    stmt = apply_text_search(stmt, SystemSkill, query)
    stmt = apply_tag_filter(stmt, SystemSkill, tags)
    stmt = stmt.order_by(SystemSkill.category.asc(), SystemSkill.name.asc())
    return list(db_session.scalars(stmt).all())


def get_system_skill(db_session: Session, entry_id: UUID) -> SystemSkill:
    entry = db_session.get(SystemSkill, entry_id)
    if entry is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Catalog skill not found")
    return entry


def get_system_skill_by_slug(db_session: Session, slug: str) -> SystemSkill | None:
    return db_session.scalar(select(SystemSkill).where(SystemSkill.slug == slug))


def create_system_skill(
    db_session: Session,
    *,
    slug: str,
    name: str,
    description: str,
    category: SystemCatalogCategory,
    tags: list[str],
    built_in_skill_id: str | None = None,
    bundle_file_id: str | None = None,
    bundle_sha256: str | None = None,
    origin: SystemCatalogOrigin = SystemCatalogOrigin.ADMIN,
) -> SystemSkill:
    if (built_in_skill_id is None) == (bundle_file_id is None):
        raise OnyxError(
            OnyxErrorCode.INVALID_INPUT,
            "A catalog skill needs exactly one of a built-in id or an uploaded bundle",
        )
    entry = SystemSkill(
        slug=normalize_catalog_slug(slug),
        name=normalize_required_text(name, field="Name", max_length=SKILL_NAME_MAX),
        description=normalize_required_text(
            description, field="Description", max_length=DESCRIPTION_MAX
        ),
        category=category,
        tags=normalize_tags(tags),
        publish_status=SystemCatalogPublishStatus.DRAFT,
        version=0,
        changelog="",
        origin=origin,
        built_in_skill_id=built_in_skill_id,
        bundle_file_id=bundle_file_id,
        bundle_sha256=bundle_sha256,
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


def update_system_skill(
    db_session: Session,
    entry: SystemSkill,
    *,
    name: str | None = None,
    description: str | None = None,
    category: SystemCatalogCategory | None = None,
    tags: list[str] | None = None,
    bundle_file_id: str | None = None,
    bundle_sha256: str | None = None,
) -> SystemSkill:
    """Update catalog metadata and, optionally, replace the bundle.

    Edits stay in the catalog until the entry is published again, so a live
    projection keeps serving the previously published content.
    """
    if name is not None:
        entry.name = normalize_required_text(
            name, field="Name", max_length=SKILL_NAME_MAX
        )
    if description is not None:
        entry.description = normalize_required_text(
            description, field="Description", max_length=DESCRIPTION_MAX
        )
    if category is not None:
        entry.category = category
    if tags is not None:
        entry.tags = normalize_tags(tags)
    if bundle_file_id is not None:
        if entry.built_in_skill_id is not None:
            raise OnyxError(
                OnyxErrorCode.INVALID_INPUT,
                "Built-in catalog skills are defined on disk and take no bundle",
            )
        entry.bundle_file_id = bundle_file_id
        entry.bundle_sha256 = bundle_sha256
    db_session.flush()
    return entry


def delete_system_skill(db_session: Session, entry: SystemSkill) -> None:
    """Delete a catalog entry.

    The caller unpublishes first, which removes the projection. Any user forks
    keep working: their ``system_skill_id`` is cleared by ``ON DELETE SET NULL``.
    """
    db_session.delete(entry)
    db_session.flush()
