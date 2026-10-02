"""Detect skills the user explicitly named in a prompt.

Prose requests like "按 financial-report-analysis 技能撰写…" carry the skill
slug verbatim, so a word-boundary match against the user's visible skills is
reliable: it never invents a binding the user did not ask for. The result
merges into the turn's/job's ``selected_skill_ids`` so skill-required MCP
servers unlock and the briefs can state the requirement.
"""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from onyx.db.models import Skill, User
from onyx.db.skill import list_runtime_skills_for_user
from onyx.utils.logger import setup_logger

logger = setup_logger()


def _skill_slug(skill: Skill) -> str | None:
    slug = (skill.built_in_skill_id or skill.name or "").strip()
    return slug or None


def detect_named_skills(db_session: Session, user: User, text: str | None) -> list[str]:
    """Skill slugs the prompt names explicitly, in the skill list's order."""
    if not text or not text.strip():
        return []
    try:
        visible = list_runtime_skills_for_user(db_session=db_session, user=user)
    except Exception:
        logger.warning("Could not list skills for prompt binding", exc_info=True)
        return []
    found: list[str] = []
    for skill in visible:
        slug = _skill_slug(skill)
        if not slug:
            continue
        # Slugs are hyphenated identifiers: treat hyphen as a word character
        # so "tax-policy-verify" never matches inside a longer slug.
        pattern = rf"(?<![\w-]){re.escape(slug)}(?![\w-])"
        if re.search(pattern, text):
            found.append(slug)
    return found


def merge_selected_skills(
    db_session: Session,
    user: User,
    text: str | None,
    selected_skill_ids: list[str] | None,
) -> list[str]:
    """Union of the chip selection and prose-named skills, order-stable."""
    merged = list(selected_skill_ids or [])
    for slug in detect_named_skills(db_session, user, text):
        if slug not in merged:
            merged.append(slug)
    return merged
