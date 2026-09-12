"""Fused financial-report-analysis skill stays parseable and scriptable."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from onyx.db.enums import SystemCatalogCategory
from onyx.skills.built_in import BUILT_IN_SKILLS, BUILTIN_SKILLS_PATH
from onyx.skills.metadata import parse_skill_document
from onyx.system_catalog.builtin.manifest import BUILT_IN_SKILL_ENTRIES

_SKILL_ID = "financial-report-analysis"
_SCRIPTS = BUILTIN_SKILLS_PATH / _SKILL_ID / "scripts"


def test_financial_report_analysis_is_registered_and_parses() -> None:
    definition = BUILT_IN_SKILLS[_SKILL_ID]
    document = parse_skill_document(
        (definition.source_dir / "SKILL.md").read_bytes(),
        directory_name=_SKILL_ID,
    )
    assert document.metadata.name == _SKILL_ID
    assert document.instructions_markdown
    assert "hithink-a-share" in (document.metadata.optional_mcp or [])
    assert "qcc-company" in (document.metadata.optional_mcp or [])
    assert "company-credit" in (document.metadata.optional_mcp or [])


def test_financial_report_analysis_is_in_the_gallery_manifest() -> None:
    entry = next(item for item in BUILT_IN_SKILL_ENTRIES if item.slug == _SKILL_ID)
    assert entry.built_in_skill_id == _SKILL_ID
    assert entry.category is SystemCatalogCategory.REPORT
    assert entry.name == "财报解读"


def test_analyze_financials_sample_detects_anomalies(tmp_path: Path) -> None:
    sample = json.loads(
        subprocess.check_output(
            [sys.executable, str(_SCRIPTS / "analyze_financials.py"), "--sample"],
            text=True,
        )
    )
    sample_path = tmp_path / "sample.json"
    sample_path.write_text(json.dumps(sample, ensure_ascii=False), encoding="utf-8")
    report = json.loads(
        subprocess.check_output(
            [
                sys.executable,
                str(_SCRIPTS / "analyze_financials.py"),
                str(sample_path),
                "--json",
            ],
            text=True,
        )
    )
    assert report["company"] == sample["company"]
    assert report["summary"]["total_anomalies"] >= 1


def test_normalize_statements_emits_trend_rows(tmp_path: Path) -> None:
    sample = subprocess.check_output(
        [sys.executable, str(_SCRIPTS / "analyze_financials.py"), "--sample"],
        text=True,
    )
    input_path = tmp_path / "statements.json"
    trend_path = tmp_path / "trend.json"
    input_path.write_text(sample, encoding="utf-8")
    summary = json.loads(
        subprocess.check_output(
            [
                sys.executable,
                str(_SCRIPTS / "normalize_statements.py"),
                "--input",
                str(input_path),
                "--trend",
                str(trend_path),
            ],
            text=True,
        )
    )
    assert summary["income_rows"] == 8
    trend = json.loads(trend_path.read_text(encoding="utf-8"))
    assert trend["income"][0]["EndDate"] == "2023-03-31"
    assert trend["income"][0]["OperatingRevenue"] == 50_000_000
    assert trend["cashflow"][-1]["NetOperateCashFlow"] == 2_000_000
