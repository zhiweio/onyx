"""Shared validation and query helpers for the three system catalog tables.

The catalog (``system_skill`` / ``system_scenario`` / ``system_report_template``)
is admin-owned metadata. It is never read at runtime: publishing projects an
entry into the matching runtime table, and every existing consumer keeps reading
the runtime tables only. See ``publish.py`` for the projection rules.
"""

from __future__ import annotations

import re
from typing import Final, TypeVar

from sqlalchemy import Select, or_

from onyx.db.enums import SystemCatalogPublishStatus
from onyx.db.models import SystemReportTemplate, SystemScenario, SystemSkill
from onyx.db.report_template import normalize_report_template_slug
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError

SLUG_MAX: Final[int] = 64
NAME_MAX: Final[int] = 128
# Skill names double as sandbox directory names, so they follow the stricter
# Agent Skills rules enforced by onyx.skills.models.SKILL_NAME_PATTERN.
SKILL_NAME_MAX: Final[int] = 64
DESCRIPTION_MAX: Final[int] = 4_000
CHANGELOG_MAX: Final[int] = 4_000
BODY_MAX: Final[int] = 100_000
TAG_MAX: Final[int] = 32
TAGS_MAX_COUNT: Final[int] = 20

# Catalog slugs use the Agent Skills shape (lowercase, hyphen-separated) so a
# skill entry's slug can be reused verbatim as its on-disk / sandbox name.
_SLUG_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

SystemCatalogModel = TypeVar(
    "SystemCatalogModel", SystemSkill, SystemScenario, SystemReportTemplate
)


def normalize_catalog_slug(raw: str) -> str:
    slug = raw.strip().lower()
    if not slug:
        raise OnyxError(OnyxErrorCode.INVALID_INPUT, "Slug is required")
    if len(slug) > SLUG_MAX:
        raise OnyxError(
            OnyxErrorCode.INVALID_INPUT,
            f"Slug must be at most {SLUG_MAX} characters",
        )
    if not _SLUG_PATTERN.fullmatch(slug):
        raise OnyxError(
            OnyxErrorCode.INVALID_INPUT,
            "Slug must contain only lowercase letters, numbers, and single hyphens",
        )
    return slug


def normalize_report_template_catalog_slug(raw: str) -> str:
    """Normalize a report template slug with the runtime table's own rules.

    ``report_template.slug`` is underscore-styled and is what scenarios
    reference. Reusing the runtime normalizer keeps a published entry's slug
    byte-identical to its projection, so the reference never breaks.
    """
    return normalize_report_template_slug(raw)


def normalize_required_text(raw: str, *, field: str, max_length: int) -> str:
    trimmed = raw.strip()
    if not trimmed:
        raise OnyxError(OnyxErrorCode.INVALID_INPUT, f"{field} is required")
    if len(trimmed) > max_length:
        raise OnyxError(
            OnyxErrorCode.INVALID_INPUT,
            f"{field} must be at most {max_length} characters",
        )
    return trimmed


def normalize_optional_text(raw: str, *, field: str, max_length: int) -> str:
    trimmed = raw.strip()
    if len(trimmed) > max_length:
        raise OnyxError(
            OnyxErrorCode.INVALID_INPUT,
            f"{field} must be at most {max_length} characters",
        )
    return trimmed


def normalize_tags(raw: list[str]) -> list[str]:
    """Lowercase, de-duplicate, and order tags so filtering is stable."""
    seen: set[str] = set()
    for tag in raw:
        trimmed = tag.strip().lower()
        if not trimmed:
            continue
        if len(trimmed) > TAG_MAX:
            raise OnyxError(
                OnyxErrorCode.INVALID_INPUT,
                f"Tag must be at most {TAG_MAX} characters",
            )
        seen.add(trimmed)
    if len(seen) > TAGS_MAX_COUNT:
        raise OnyxError(
            OnyxErrorCode.INVALID_INPUT,
            f"At most {TAGS_MAX_COUNT} tags are allowed",
        )
    return sorted(seen)


def apply_text_search(
    stmt: Select[tuple[SystemCatalogModel]],
    model: type[SystemCatalogModel],
    query: str | None,
) -> Select[tuple[SystemCatalogModel]]:
    if query is None:
        return stmt
    trimmed = query.strip()
    if not trimmed:
        return stmt
    pattern = f"%{trimmed.lower()}%"
    return stmt.where(
        or_(
            model.name.ilike(pattern),
            model.slug.ilike(pattern),
            model.description.ilike(pattern),
        )
    )


def apply_tag_filter(
    stmt: Select[tuple[SystemCatalogModel]],
    model: type[SystemCatalogModel],
    tags: list[str] | None,
) -> Select[tuple[SystemCatalogModel]]:
    """Keep entries carrying every requested tag (AND semantics)."""
    if not tags:
        return stmt
    normalized = normalize_tags(tags)
    for tag in normalized:
        stmt = stmt.where(model.tags.contains([tag]))
    return stmt


def require_published(entry: SystemCatalogModel) -> SystemCatalogModel:
    """Guard for user-facing gallery reads.

    Drafts and archived entries are reported as missing rather than forbidden:
    a user has no way to learn they exist, so 404 is the honest answer.
    """
    if entry.publish_status is not SystemCatalogPublishStatus.PUBLISHED:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Catalog entry not found")
    return entry
