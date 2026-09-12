from unittest.mock import MagicMock

from onyx.skills.effective_mcp import (
    load_skill_mcp_spec,
    resolve_effective_mcp_server_ids,
    slugs_for_skill_spec,
)


def test_zhihuiya_skill_enables_starter_group_only() -> None:
    spec = load_skill_mcp_spec("zhihuiya")
    assert spec is not None
    assert spec.default_group == "zhihuiya-starter"
    slugs = slugs_for_skill_spec(spec)
    assert slugs == {
        "pharma-intelligence",
        "patsnap-search",
        "biology-modality",
        "patent-analysis",
        "patent-briefing",
        "company-credit",
    }
    assert "patent-landscape" not in slugs
    assert "triz" not in slugs


def test_empty_turn_selects_no_servers() -> None:
    assert resolve_effective_mcp_server_ids(MagicMock(), MagicMock()) == []


def test_empty_selection_has_no_skill_slugs() -> None:
    spec = load_skill_mcp_spec("docx")
    assert spec is not None
    assert slugs_for_skill_spec(spec) == set()


def test_hithink_skill_requires_all_six() -> None:
    spec = load_skill_mcp_spec("hithink-finance")
    assert spec is not None
    slugs = slugs_for_skill_spec(spec)
    assert slugs == {
        "hithink-a-share",
        "hithink-a-share-index",
        "hithink-meta",
        "hithink-fund",
        "hithink-futures",
        "hithink-options",
    }


def test_qichacha_router_exposes_ten_official_servers() -> None:
    spec = load_skill_mcp_spec("qichacha")
    assert spec is not None
    assert spec.required == ()
    assert slugs_for_skill_spec(spec) == {
        "qcc-company",
        "qcc-risk",
        "qcc-ipr",
        "qcc-operation",
        "qcc-history",
        "qcc-executive",
        "qcc-legal-regulation",
        "qcc-legal-case",
        "qcc-tender",
        "qcc-document",
    }


def test_kyb_skill_requires_company_and_risk() -> None:
    spec = load_skill_mcp_spec("kyb-verification-qcc")
    assert spec is not None
    assert spec.required == ("qcc-company", "qcc-risk")
    assert "qcc-history" in spec.optional
    assert "qcc-executive" in spec.optional


def test_contract_review_uses_official_company_and_risk() -> None:
    spec = load_skill_mcp_spec("contract-review")
    assert spec is not None
    assert spec.required == ("qcc-company", "qcc-risk")
