"""Read a catalog skill's SKILL.md body for admin and gallery previews."""

from __future__ import annotations

from sqlalchemy.orm import Session

from onyx.db.models import SystemSkill
from onyx.db.system_catalog.publish import find_projected_skill
from onyx.file_store.file_store import get_default_file_store
from onyx.skills.built_in import BUILT_IN_SKILLS
from onyx.skills.bundle import read_custom_bundle_instructions
from onyx.skills.content import (
    read_builtin_skill_instructions,
    read_custom_skill_bundle_instructions,
)


def read_catalog_skill_instructions(
    db_session: Session, entry: SystemSkill
) -> str | None:
    """Return the SKILL.md body, or None when the source is missing.

    Built-in entries read from disk. Uploaded entries read the catalog
    bundle first so a draft still has a preview before publish.
    """
    if entry.built_in_skill_id is not None:
        definition = BUILT_IN_SKILLS.get(entry.built_in_skill_id)
        if definition is None:
            return None
        return read_builtin_skill_instructions(definition)
    if entry.bundle_file_id is not None:
        try:
            bundle_bytes = get_default_file_store().read_file(entry.bundle_file_id).read()
            return read_custom_bundle_instructions(bundle_bytes)
        except Exception:
            return None
    projection = find_projected_skill(db_session, entry)
    if projection is None:
        return None
    return read_custom_skill_bundle_instructions(projection)
