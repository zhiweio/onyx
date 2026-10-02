"""Deterministic post-checks for rendered contract-style reports.

The checks gate mechanics, not content: placeholder residue, table-of-
contents presence, disclaimer survival, figure count, chapter-number
continuity and source-line coverage. They run on the rendered .docx bytes
so what is checked is exactly what the reader gets.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from typing import Final

from onyx.report_templates.contract import ReportContract, parse_contract

_CN_NUMERALS: Final[str] = "一二三四五六七八九十"

# A source line under a table/figure: 来源/资料来源/数据来源 followed by a
# page, URL or named source.
_SOURCE_LINE: Final[re.Pattern[str]] = re.compile(
    r"(来源|资料来源|数据来源)[::].*(第\s*\d+|http|年报|年报|公告|巨潮|企查查|智慧芽|同花顺|iFinD)",
    re.M,
)

_DISCLAIMER_TEXT: Final[re.Pattern[str]] = re.compile(r"免责声明|不构成投资建议")

_CHAPTER_HEADING: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:#{1,6}\s+)?第?\s*([一二三四五六七八九十]{1,3})\s*[、章节.．]|"
    r"^\s*(?:#{1,6}\s+)?(\d{1,2})[.．、]\s*\S"
)


@dataclass(frozen=True)
class Finding:
    """One post-check outcome. ``passed`` findings are informational."""

    check: str
    passed: bool
    detail: str


def _document_xml(docx_bytes: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as archive:
        return archive.read("word/document.xml").decode("utf-8", errors="replace")


def _visible_text(document_xml: str) -> str:
    """Reader-visible text, one line per paragraph."""
    lines: list[str] = []
    for paragraph in re.finditer(r"<w:p\b[^>]*>(.*?)</w:p>", document_xml, re.S):
        content = "".join(
            match.group(1)
            for match in re.finditer(r"<w:t[^>]*>([^<]*)</w:t>", paragraph.group(1))
        )
        if content.strip():
            lines.append(content)
    return "\n".join(lines)


def check_report(docx_bytes: bytes, contract_raw: dict | None = None) -> list[Finding]:
    """Run every mechanical check; returns findings in a stable order."""
    contract: ReportContract = parse_contract(contract_raw)
    document_xml = _document_xml(docx_bytes)
    text = _visible_text(document_xml)
    findings: list[Finding] = []

    leftover = re.findall(r"\{\{[^}]{0,80}}", text)
    findings.append(
        Finding(
            check="placeholders",
            passed=not leftover,
            detail=(
                "no placeholder residue"
                if not leftover
                else f"leftover placeholders: {leftover[:5]}"
            ),
        )
    )

    if contract.require_toc:
        has_toc = "TOC" in document_xml and "instrText" in document_xml
        findings.append(
            Finding(
                check="toc",
                passed=has_toc,
                detail="TOC field present" if has_toc else "TOC field missing",
            )
        )

    if contract.require_disclaimer:
        has_disclaimer = bool(_DISCLAIMER_TEXT.search(text))
        findings.append(
            Finding(
                check="disclaimer",
                passed=has_disclaimer,
                detail=(
                    "disclaimer present" if has_disclaimer else "disclaimer missing"
                ),
            )
        )

    figure_count = document_xml.count("<w:drawing>")
    figures_ok = figure_count >= contract.min_figures
    findings.append(
        Finding(
            check="figures",
            passed=figures_ok,
            detail=(f"{figure_count} figures (required >= {contract.min_figures})"),
        )
    )

    findings.append(_check_chapter_numbering(text))

    source_lines = len(_SOURCE_LINE.findall(text))
    findings.append(
        Finding(
            check="sources",
            passed=source_lines > 0,
            detail=f"{source_lines} source lines found",
        )
    )

    # Image/link targets may legitimately point into the workspace; only
    # paths written in prose are leaks.
    prose = re.sub(r"\]\([^)]*\)", "()", text)
    internal_paths = re.findall(r"outputs/[\w./-]+|\.opencode/[\w./-]+", prose)
    findings.append(
        Finding(
            check="internal_paths",
            passed=not internal_paths,
            detail=(
                "no internal paths in reader-visible text"
                if not internal_paths
                else f"internal paths leaked: {sorted(set(internal_paths))[:5]}"
            ),
        )
    )

    return findings


def _check_chapter_numbering(text: str) -> Finding:
    """Top-level chapters must number continuously (一、二、… or 1. 2. …)."""
    style: str | None = None
    expected = 1
    for line in text.split("\n"):
        match = _CHAPTER_HEADING.match(line)
        if match is None:
            continue
        cn, ar = match.group(1), match.group(2)
        if cn is not None:
            current = _cn_numeral_value(cn)
            detected = "cn"
        else:
            current = int(ar)
            detected = "arabic"
        if style is None:
            style = detected
        elif style != detected:
            continue
        if current != expected:
            return Finding(
                check="chapter_numbering",
                passed=False,
                detail=f"chapter number {current} out of sequence (expected {expected})",
            )
        expected += 1
    return Finding(
        check="chapter_numbering",
        passed=True,
        detail="chapter numbers continuous" if style else "no numbered chapters",
    )


def _cn_numeral_value(text: str) -> int:
    """Value of a simple Chinese numeral up to 九十九 (chapter-style)."""
    if text == "十":
        return 10
    if "十" in text:
        tens, _, ones = text.partition("十")
        tens_value = _CN_NUMERALS.index(tens) + 1 if tens else 1
        ones_value = _CN_NUMERALS.index(ones) + 1 if ones else 0
        return tens_value * 10 + ones_value
    return _CN_NUMERALS.index(text) + 1


def report_passes(findings: list[Finding]) -> bool:
    return all(finding.passed for finding in findings)


# --------------------------------------------------------------------------- #
# Markdown-level checks (agent self-check before rendering)
# --------------------------------------------------------------------------- #
_ELEMENT_HINTS: Final[dict[str, re.Pattern[str]]] = {
    "kpi_dashboard": re.compile(r"```kpi|看板|核心指标"),
    "risk_matrix": re.compile(r"风险矩阵|风险评分"),
    "remediation": re.compile(r"整改|改进建议|优先级"),
    "subsequent_events": re.compile(r"期后事项|期后"),
    "data_gaps": re.compile(r"数据缺口|未获取"),
    "sources": re.compile(r"来源|资料来源"),
    "disclaimer": re.compile(r"免责声明|不构成投资建议"),
}


def check_report_markdown(
    md_text: str, contract_raw: dict | None = None
) -> list[Finding]:
    """Run the contract's mechanical checks against report markdown.

    This is what the sandbox-side ``check_report`` platform tool runs so an
    agent can self-check before delivering. TOC is not checked here: the
    renderer inserts it at export time.
    """
    contract: ReportContract = parse_contract(contract_raw)
    findings: list[Finding] = []

    leftover = re.findall(r"\{\{[^}]{0,80}", md_text)
    findings.append(
        Finding(
            check="placeholders",
            passed=not leftover,
            detail=(
                "no placeholder residue"
                if not leftover
                else f"leftover placeholders: {leftover[:5]}"
            ),
        )
    )

    if contract.require_disclaimer:
        findings.append(
            Finding(
                check="disclaimer",
                passed=bool(_DISCLAIMER_TEXT.search(md_text)),
                detail="disclaimer present or missing",
            )
        )

    figure_count = len(re.findall(r"!\[[^\]]*\]\([^)]+\)", md_text))
    findings.append(
        Finding(
            check="figures",
            passed=figure_count >= contract.min_figures,
            detail=f"{figure_count} figures (required >= {contract.min_figures})",
        )
    )

    findings.append(_check_chapter_numbering(md_text))

    findings.append(
        Finding(
            check="sources",
            passed=bool(_SOURCE_LINE.search(md_text)),
            detail="source lines present or missing",
        )
    )

    prose = re.sub(r"\]\([^)]*\)", "()", md_text)
    internal_paths = re.findall(r"outputs/[\w./-]+|\.opencode/[\w./-]+", prose)
    findings.append(
        Finding(
            check="internal_paths",
            passed=not internal_paths,
            detail=(
                "no internal paths"
                if not internal_paths
                else f"internal paths leaked: {sorted(set(internal_paths))[:5]}"
            ),
        )
    )

    missing_elements = [
        element
        for element in contract.required_elements
        if (pattern := _ELEMENT_HINTS.get(element)) is not None
        and not pattern.search(md_text)
    ]
    findings.append(
        Finding(
            check="required_elements",
            passed=not missing_elements,
            detail=(
                "all required elements present"
                if not missing_elements
                else f"missing elements: {missing_elements}"
            ),
        )
    )

    return findings
