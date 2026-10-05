"""The tax-compliance-check scenario binds its contract template properly."""

from __future__ import annotations

from onyx.db.enums import SystemCatalogCategory
from onyx.system_catalog.builtin.manifest import (
    BUILT_IN_REPORT_TEMPLATE_ENTRIES,
    BUILT_IN_SCENARIO_ENTRIES,
)


def test_compliance_template_entry_is_contract_style() -> None:
    entry = next(
        item
        for item in BUILT_IN_REPORT_TEMPLATE_ENTRIES
        if item.slug == "tax_compliance_check"
    )
    assert entry.is_contract_style
    contract = entry.read_contract()
    assert contract["min_figures"] >= 5
    # No theme file: the renderer default palette applies at export.
    assert entry.read_theme() in ({}, None) or entry.read_theme().get("accent")
    body = entry.read_body()
    assert "check_report" in body
    assert "MCP" in body  # hard rule keeps tool names out of the report


def test_compliance_scenario_binds_the_template() -> None:
    entry = next(
        item
        for item in BUILT_IN_SCENARIO_ENTRIES
        if item.slug == "tax-compliance-check"
    )
    assert entry.report_template_slug == "tax_compliance_check"
    assert entry.category is SystemCatalogCategory.TAX
    rules = entry.read_rules()
    gates = " ".join(rules["quality_gates"])
    assert "check_report" in gates
    deliverables = " ".join(rules["deliverables"])
    assert "outputs/report.md" in deliverables
    assert "report.docx" not in deliverables
