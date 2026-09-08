from pathlib import Path

from onyx.skills.built_in import BUILTIN_SKILLS_PATH, BUILT_IN_SKILLS
from onyx.skills.metadata import parse_skill_document

_FORBIDDEN = (
    "丁香园",
    "dxy-pharma-data",
    "dxy-insight",
    "dxy-insight-mcp",
    "list_data_apis",
    "get_data_api_schema",
    "replay_store",
    "search_global_pipeline",
    "search_therapeutic_landscape",
    "search_trial_result",
    "search_domestic_registration",
    "search_pharmaceutical_news",
    "patsnap",
    "智慧芽",
)


def test_clinical_initiation_skill_is_registered_and_parses() -> None:
    definition = BUILT_IN_SKILLS["biomed-clinical-initiation"]
    source = definition.source_dir / "SKILL.md"
    document = parse_skill_document(
        source.read_bytes(),
        directory_name="biomed-clinical-initiation",
    )
    assert document.metadata.name == "biomed-clinical-initiation"
    assert "clinical-stage" in document.metadata.description
    assert "立项" in document.metadata.description
    assert source == BUILTIN_SKILLS_PATH / "biomed-clinical-initiation" / "SKILL.md"


def test_clinical_initiation_skill_uses_public_search_not_dxy() -> None:
    text = Path(
        BUILTIN_SKILLS_PATH / "biomed-clinical-initiation" / "SKILL.md"
    ).read_text(encoding="utf-8")
    lowered = text.lower()
    for token in _FORBIDDEN:
        assert token.lower() not in lowered
    assert "web_search" in text
    assert "webfetch" in text
    assert "ClinicalTrials.gov" in text
    assert "PubMed" in text
    assert "Espacenet" in text
    assert "GLOBOCAN" in text
