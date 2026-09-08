from pathlib import Path

from onyx.skills.built_in import BUILTIN_SKILLS_PATH, BUILT_IN_SKILLS
from onyx.skills.metadata import parse_skill_document

_FORBIDDEN = (
    "patsnap",
    "智慧芽",
    "replay_store",
    "PATSNAP_MCP",
    "ls_antibody_antigen_search",
    "patsnap_fetch",
)


def test_adc_dac_skill_is_registered_and_parses() -> None:
    definition = BUILT_IN_SKILLS["biomed-adc-dac-initiation"]
    source = definition.source_dir / "SKILL.md"
    document = parse_skill_document(
        source.read_bytes(),
        directory_name="biomed-adc-dac-initiation",
    )
    assert document.metadata.name == "biomed-adc-dac-initiation"
    assert "ADC" in document.metadata.description
    assert source == BUILTIN_SKILLS_PATH / "biomed-adc-dac-initiation" / "SKILL.md"


def test_adc_dac_skill_uses_public_search_not_patsnap() -> None:
    text = Path(
        BUILTIN_SKILLS_PATH / "biomed-adc-dac-initiation" / "SKILL.md"
    ).read_text(encoding="utf-8")
    lowered = text.lower()
    for token in _FORBIDDEN:
        assert token.lower() not in lowered
    assert "web_search" in text
    assert "webfetch" in text
    assert "PubMed" in text
    assert "Espacenet" in text
