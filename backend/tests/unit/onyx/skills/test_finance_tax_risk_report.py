"""The finance-tax-risk-report skill stays parseable, scriptable, and templated."""

from __future__ import annotations

import json
import subprocess
import sys

from onyx.db.enums import SystemCatalogCategory
from onyx.skills.built_in import BUILT_IN_SKILLS, BUILTIN_SKILLS_PATH
from onyx.skills.metadata import parse_skill_document
from onyx.system_catalog.builtin.manifest import (
    BUILT_IN_REPORT_TEMPLATE_ENTRIES,
    BUILT_IN_SCENARIO_ENTRIES,
    BUILT_IN_SKILL_ENTRIES,
)

_SKILL_ID = "finance-tax-risk-report"
_SCRIPTS = BUILTIN_SKILLS_PATH / _SKILL_ID / "scripts"


def test_skill_is_registered_and_parses() -> None:
    definition = BUILT_IN_SKILLS[_SKILL_ID]
    document = parse_skill_document(
        (definition.source_dir / "SKILL.md").read_bytes(),
        directory_name=_SKILL_ID,
    )
    assert document.metadata.name == _SKILL_ID
    assert document.instructions_markdown
    optional = document.metadata.optional_mcp or []
    assert "hithink-a-share" in optional
    assert "qcc-company" in optional
    assert "company-credit" in optional


def test_skill_is_in_the_gallery_manifest() -> None:
    entry = next(item for item in BUILT_IN_SKILL_ENTRIES if item.slug == _SKILL_ID)
    assert entry.built_in_skill_id == _SKILL_ID
    assert entry.category is SystemCatalogCategory.REPORT
    assert entry.name == "财税与经营风险分析报告"


def test_report_template_entry_renders_contract_sample() -> None:
    entry = next(
        item
        for item in BUILT_IN_REPORT_TEMPLATE_ENTRIES
        if item.slug == "finance_tax_risk_report"
    )
    # Contract-style: structured contract (+ optional theme) drive a rendered
    # sample document instead of a fill-in skeleton.
    assert entry.is_contract_style
    contract = entry.read_contract()
    assert "风险矩阵" in entry.read_body()
    assert contract["required_elements"]
    assert contract["min_figures"] >= 5
    assert entry.read_theme()["accent"]

    from onyx.report_templates.renderer import build_sample_docx

    docx_bytes = build_sample_docx(contract, entry.read_theme())
    assert docx_bytes.startswith(b"PK")


def test_scenario_entry_binds_skill_and_template() -> None:
    entry = next(item for item in BUILT_IN_SCENARIO_ENTRIES if item.slug == _SKILL_ID)
    assert _SKILL_ID in entry.skill_slugs
    assert entry.report_template_slug == "finance_tax_risk_report"
    rules = entry.read_rules()
    assert rules["domain"] == "listed-company"
    gates = " ".join(rules["quality_gates"])
    assert "original source" in gates
    assert "server slugs" in gates


def test_report_citations_use_original_sources() -> None:
    definition = BUILT_IN_SKILLS[_SKILL_ID]
    instructions = parse_skill_document(
        (definition.source_dir / "SKILL.md").read_bytes(),
        directory_name=_SKILL_ID,
    ).instructions_markdown
    assert "MCP 工具名" in instructions
    assert "原始来源名称" in instructions
    checklist = (
        definition.source_dir / "references" / "quality-checklist.md"
    ).read_text(encoding="utf-8")
    assert "内部路径" in checklist
    assert "企查查" in checklist


def test_compute_metrics_sample_matches_statements() -> None:
    statements = json.loads(
        subprocess.check_output(
            [
                sys.executable,
                str(_SCRIPTS / "compute_metrics.py"),
                "--sample-statements",
            ],
            text=True,
        )
    )
    dashboard = json.loads(
        subprocess.check_output(
            [sys.executable, str(_SCRIPTS / "compute_metrics.py"), "--sample"],
            text=True,
        )
    )
    assert dashboard["years"] == statements["years"]
    rows = {row["metric"]: row["values"] for row in dashboard["rows"]}
    revenue = statements["income"]["revenue"]
    cost = statements["income"]["cost"]
    for index in range(len(revenue)):
        expected_gross = (1.0 - cost[index] / revenue[index]) * 100.0
        assert abs(rows["毛利率"][index] - expected_gross) < 0.05
        expected_receipts = (
            statements["cashflow"]["sales_receipts"][index] / revenue[index]
        )
        assert abs(rows["收现比"][index] - expected_receipts) < 0.005
    assert rows["收现比"][0] > 1.0
    assert rows["简化自由现金流"][-2] < 0


def test_extract_annual_report_self_test() -> None:
    output = subprocess.check_output(
        [sys.executable, str(_SCRIPTS / "extract_annual_report.py"), "--self-test"],
        text=True,
    )
    assert "self-test passed" in output


def test_check_report_gates_the_starter_template() -> None:
    """The starter template teaches components; the gate flags an unfilled one.

    The unfilled skeleton carries {{placeholders}} on purpose. A minimal
    compliant report (all elements, figures, sources) must pass every check.
    """
    from onyx.report_templates.postcheck import check_report_markdown

    template = (
        BUILTIN_SKILLS_PATH / _SKILL_ID / "assets" / "report_template.md"
    ).read_text(encoding="utf-8")
    contract = next(
        item
        for item in BUILT_IN_REPORT_TEMPLATE_ENTRIES
        if item.slug == "finance_tax_risk_report"
    ).read_contract()

    findings = check_report_markdown(template, contract)
    failed = {finding.check for finding in findings if not finding.passed}
    assert "placeholders" in failed

    compliant = "\n".join(
        [
            "# 一、执行摘要",
            "```kpi",
            "营业收入 | 4.73 亿元 | 关注",
            "毛利率 | 35.6% | 稳健",
            "```",
            "来源: 公司2024年年度报告第 5 页。",
            "# 二、风险",
            "| 编号 | 风险点 | 等级 | 风险评分 | 处置建议 |",
            "| --- | --- | --- | --- | --- |",
            "| TX-01 | 税负率异常 | 高 | 56 | 立即治理 |",
            "![图](outputs/charts/01.png)",
            "![图](outputs/charts/02.png)",
            "![图](outputs/charts/03.png)",
            "![图](outputs/charts/04.png)",
            "![图](outputs/charts/05.png)",
            "# 三、整改与期后",
            "30 日内完成整改;期后事项未经审计,仅作趋势观察。",
            "数据缺口:前五大客户明细未获取。",
            "## 免责声明",
            "本报告不构成投资建议。",
        ]
    )
    findings = check_report_markdown(compliant, contract)
    failures = [
        f"{finding.check}: {finding.detail}"
        for finding in findings
        if not finding.passed
    ]
    assert failures == []
