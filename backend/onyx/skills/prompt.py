"""Load selected skill bodies into a Chat prompt prefix."""

from __future__ import annotations

from collections.abc import Sequence

from onyx.skills.built_in import BUILT_IN_SKILLS
from onyx.skills.metadata import parse_skill_document


def build_selected_skill_prompt(skill_ids: Sequence[str] | None) -> str | None:
    """Return SKILL.md bodies for built-in skills the user picked.

    Chat has no sandbox, so the model reads the instructions inline. Craft
    still pushes skill files and only uses this when we inject extra context.
    """
    if not skill_ids:
        return None
    parts: list[str] = []
    for skill_id in skill_ids:
        definition = BUILT_IN_SKILLS.get(skill_id)
        if definition is None:
            continue
        source_name = "SKILL.md.template" if definition.has_template else "SKILL.md"
        source_path = definition.source_dir / source_name
        if not source_path.is_file():
            continue
        document = parse_skill_document(
            source_path.read_bytes(), directory_name=skill_id
        )
        parts.append(
            f"## Skill: {document.metadata.name}\n\n{document.instructions_markdown.strip()}"
        )
    if not parts:
        return None
    return (
        "The user selected these skills. Follow their instructions.\n\n"
        + "\n\n".join(parts)
    )
