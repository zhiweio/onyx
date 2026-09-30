"""Rewritten tax skills must not reference their upstream private services."""

from pathlib import Path

import pytest

from onyx.skills.built_in import BUILTIN_SKILLS_PATH

REWRITTEN_SKILL_IDS = ("tax-policy-verify", "caishui-skill", "tax-tax-audit")

FORBIDDEN_MARKERS = (
    "aitaxs",
    "matrix_install",
    "matrix.json",
    "SkillHub",
    "专家团",
    "inteliway",
)


def _skill_files(skill_id: str) -> list[Path]:
    skill_dir = BUILTIN_SKILLS_PATH / skill_id
    return [path for path in skill_dir.rglob("*") if path.is_file()]


@pytest.mark.parametrize("skill_id", REWRITTEN_SKILL_IDS)
def test_rewritten_skill_carries_no_private_service_references(
    skill_id: str,
) -> None:
    for path in _skill_files(skill_id):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for marker in FORBIDDEN_MARKERS:
            assert marker not in text, (skill_id, path.name, marker)
