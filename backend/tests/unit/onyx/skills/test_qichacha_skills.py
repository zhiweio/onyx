from pathlib import Path

from onyx.skills.built_in import BUILTIN_SKILLS_PATH, BUILT_IN_SKILLS
from onyx.skills.metadata import parse_skill_document

_QICHACHA_SKILL_IDS = (
    "qichacha",
    "contract-review",
    "listed-co-credit-legal",
    "listed-co-entity-resolve",
    "kyb-verification-qcc",
    "litigation-analysis-qcc",
    "credit-due-diligence-qcc",
    "counterparty-risk-qcc",
    "ubo-screening-qcc",
    "trade-finance-compliance-qcc",
    "credit-monitoring-qcc",
    "equity-structure-qcc",
    "executive-background-qcc",
    "business-health-scan-qcc",
    "guarantor-check-qcc",
    "bankruptcy-monitor-qcc",
    "ic-memo-qcc",
    "history-evolution-qcc",
    "strip-profile-qcc",
    "competitor-analysis-qcc",
    "fundraising-tracker-qcc",
    "ip-asset-inventory-qcc",
    "contract-party-check-qcc",
    "labor-compliance-qcc",
    "ip-infringement-alert-qcc",
    "debt-recovery-assessment-qcc",
    "license-validation-qcc",
    "vendor-assessment-qcc",
    "supplier-annual-check-qcc",
    "new-supplier-screening-qcc",
)

_CLI_TOKENS = (
    "qcc company ",
    "qcc init",
    "npm install -g qcc-agent-cli",
    "pip install qcc-cli",
    "pip install qcc-agent-cli",
)


def test_qichacha_skills_parse_and_forbid_cli() -> None:
    for skill_id in _QICHACHA_SKILL_IDS:
        definition = BUILT_IN_SKILLS[skill_id]
        source = definition.source_dir / "SKILL.md"
        document = parse_skill_document(
            source.read_bytes(),
            directory_name=skill_id,
        )
        assert document.metadata.name == skill_id
        text = source.read_text(encoding="utf-8")
        assert "qcc-agent-cli" in text
        assert "Do not run `qcc`" in text
        for token in _CLI_TOKENS:
            assert token not in text, f"{skill_id} still teaches {token!r}"


def test_qichacha_router_points_at_official_guide() -> None:
    text = Path(BUILTIN_SKILLS_PATH / "qichacha" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "https://agent.qcc.com/guide" in text
    assert "references/mcp.md" in text
    mcp = Path(BUILTIN_SKILLS_PATH / "qichacha" / "references" / "mcp.md").read_text(
        encoding="utf-8"
    )
    assert "https://agent.qcc.com/mcp/{server}/stream" in mcp
    assert "Do not run `qcc`" in mcp
