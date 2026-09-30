"""The finance-tax-risk-report skill stays parseable, scriptable, and templated."""

from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

from onyx.db.enums import ReportTemplateKind, SystemCatalogCategory
from onyx.skills.built_in import BUILT_IN_SKILLS, BUILTIN_SKILLS_PATH
from onyx.skills.metadata import parse_skill_document
from onyx.system_catalog.builtin.manifest import (
    BUILT_IN_REPORT_TEMPLATE_ENTRIES,
    BUILT_IN_SCENARIO_ENTRIES,
    BUILT_IN_SKILL_ENTRIES,
)
from onyx.system_catalog.builtin.word.generate import generate_official_docx

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


def test_report_template_entry_generates_docx() -> None:
    entry = next(
        item
        for item in BUILT_IN_REPORT_TEMPLATE_ENTRIES
        if item.slug == "finance_tax_risk_report"
    )
    assert entry.kind is ReportTemplateKind.DOCX
    body = entry.read_body()
    assert "风险矩阵" in body
    docx_bytes = generate_official_docx("finance_tax_risk_report")
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
    assert "零内部痕迹" in checklist
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


def test_build_report_docx_renders_template(tmp_path: Path) -> None:
    from docx import Document

    template = BUILTIN_SKILLS_PATH / _SKILL_ID / "assets" / "report_template.md"
    output = tmp_path / "report.docx"
    subprocess.check_output(
        [
            sys.executable,
            str(_SCRIPTS / "build_report_docx.py"),
            "--input",
            str(template),
            "--output",
            str(output),
        ],
        text=True,
    )
    assert output.read_bytes().startswith(b"PK")
    document = Document(str(output))
    with zipfile.ZipFile(output) as bundle:
        document_xml = bundle.read("word/document.xml").decode("utf-8")
    assert "TOC" in document_xml
    headings = [
        p.text
        for p in document.paragraphs
        if p.style is not None and p.style.name.startswith("Heading")
    ]
    assert len(headings) >= 12
    assert headings[0].startswith("一、")
    assert any(text.startswith("二、") for text in headings)
    assert not any("草稿" in text for text in headings)
