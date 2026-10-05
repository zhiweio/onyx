"""Per-session skill subset: which skills land in ``.opencode/skills``.

opencode injects every linked skill's name+description into the ``skill``
tool description on every LLM call. Linking all ~137 built-ins costs
roughly 12K tokens per call, so a session links only its effective set:

    core delivery skills ∪ scenario-bound skills ∪ user-picked chips

Skills named in prose or picked mid-conversation extend the set at turn
entry (see ``SessionManager.extend_session_skills``), so the catalog never
blocks a user request — it only stops paying for skills nobody bound.
"""

from __future__ import annotations

import re
from typing import Sequence

from sqlalchemy.orm import Session

from onyx.db.models import User
from onyx.db.skill import list_runtime_skills_for_user
from onyx.server.features.build.skill_binding import resolve_skill_refs_to_slugs
from onyx.utils.logger import setup_logger

logger = setup_logger()

# Delivery-format skills every session may need without asking: they are
# small, cheap in the catalog, and missing them breaks the most common
# outputs (documents, decks, sheets, reports, the long-job protocol).
CORE_DELIVERY_SKILL_SLUGS: tuple[str, ...] = (
    "docx",
    "pptx",
    "xlsx",
    "pdf",
    "slideblocks",
    "long-job-protocol",
)

_SLUG_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def sanitize_skill_slug(slug: str) -> str | None:
    """A slug safe to embed in a shell symlink target. None when unsafe."""
    text = (slug or "").strip()
    if not _SLUG_PATTERN.fullmatch(text):
        return None
    return text


def visible_skill_slugs(db_session: Session, user: User) -> set[str]:
    try:
        return {
            slug
            for skill in list_runtime_skills_for_user(db_session=db_session, user=user)
            if (slug := (skill.built_in_skill_id or skill.name or "").strip())
        }
    except Exception:
        logger.warning("Could not list runtime skills for subset", exc_info=True)
        return set()


def compute_session_skill_slugs(
    db_session: Session,
    user: User,
    *,
    scenario_skill_refs: Sequence[str] | None = None,
    selected_skill_ids: Sequence[str] | None = None,
    extra_slugs: Sequence[str] | None = None,
    visible: set[str] | None = None,
) -> list[str]:
    """Ordered, de-duplicated effective subset, filtered to real skills.

    ``visible`` may carry a pre-fetched visible-slug set to avoid a second
    query per turn; when it is None the set is fetched here.
    """
    if visible is None:
        visible = visible_skill_slugs(db_session, user)
    ordered: list[str] = list(CORE_DELIVERY_SKILL_SLUGS)
    if scenario_skill_refs:
        ordered.extend(
            resolve_skill_refs_to_slugs(db_session, list(scenario_skill_refs))
        )
    ordered.extend(selected_skill_ids or [])
    ordered.extend(extra_slugs or [])
    seen: set[str] = set()
    result: list[str] = []
    for raw in ordered:
        slug = sanitize_skill_slug(raw)
        if slug is None or slug in seen:
            continue
        seen.add(slug)
        # Keep unknown slugs out of the links: a dangling symlink in the
        # skills dir is a catalog entry for a skill that cannot load.
        if not visible or slug in visible:
            result.append(slug)
    return result
