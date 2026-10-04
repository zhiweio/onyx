#!/usr/bin/env python3
"""Self-check a finished report (HTML / Word / Markdown) before delivery.

Gates mechanics, not content: placeholder residue, internal or temp path
leaks, MCP server/tool names, draft markers, figure count, source lines
and the disclaimer survival. The scanned surface depends on the file type:

- ``.docx``: reader-visible text of ``word/document.xml`` paragraphs.
- ``.html``: the raw payload. A single-file offline build keeps the
  reader-visible copy inside inline scripts, so the whole payload is the
  text surface; ``TODO``/``FIXME`` stay excluded there because bundled
  library code may contain them.
- ``.md``: full text with markdown link targets stripped.

Exit code 0 when every check passes, 1 otherwise. Stdlib only: this runs
inside the sandbox without the onyx package.
"""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Final

_PLACEHOLDER: Final[re.Pattern[str]] = re.compile(r"\{\{[^}]{0,80}")

_INTERNAL_PATH: Final[re.Pattern[str]] = re.compile(
    r"outputs/[\w./-]+|\.opencode/[\w./-]+|\.slideblocks/[\w./-]+"
    r"|/tmp/[\w./-]+|/workspace/[\w./-]+"
)

_MCP_SLUG: Final[re.Pattern[str]] = re.compile(
    r"\b(?:qcc|patsnap|hithink)-[\w-]+"
    r"|\bcompany-(?:credit|profile|risk)\b"
    r"|\bMCP\b"
)

# CJK draft markers are safe on any surface; ASCII ones only on text we
# know is reader-visible, so bundled JS cannot false-positive.
_DIRTY_CJK: Final[re.Pattern[str]] = re.compile(r"草稿|待修改|待补充|待完善|待定稿")
_DIRTY_ASCII: Final[re.Pattern[str]] = re.compile(r"\b(?:TODO|FIXME)\b")

_SOURCE_LINE: Final[re.Pattern[str]] = re.compile(
    r"(来源|资料来源|数据来源)[::：].*"
    r"(第\s*\d+|https?://|年报|季报|定期报告|公告|巨潮|企查查|智慧芽|同花顺|iFinD|交易所|公司官网)",
    re.M,
)

_DISCLAIMER: Final[re.Pattern[str]] = re.compile(r"免责声明|不构成投资建议")

_MD_IMAGE: Final[re.Pattern[str]] = re.compile(r"!\[[^\]]*\]\([^)]+\)")
_MD_LINK: Final[re.Pattern[str]] = re.compile(r"\]\([^)]*\)")


@dataclass(frozen=True)
class Finding:
    """One self-check outcome. ``passed`` findings are informational."""

    check: str
    passed: bool
    detail: str


class _VisibleHtmlText(HTMLParser):
    """Collect text nodes outside <script>/<style>."""

    _SKIP = frozenset({"script", "style"})

    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth and data.strip():
            self._chunks.append(data.strip())

    def text(self) -> str:
        return "\n".join(self._chunks)


def _docx_surface(path: Path) -> tuple[str, int]:
    """Reader-visible text and figure count of a .docx file."""
    with zipfile.ZipFile(path) as archive:
        document_xml = archive.read("word/document.xml").decode(
            "utf-8", errors="replace"
        )
    lines: list[str] = []
    for paragraph in re.finditer(r"<w:p\b[^>]*>(.*?)</w:p>", document_xml, re.S):
        content = "".join(
            match.group(1)
            for match in re.finditer(r"<w:t[^>]*>([^<]*)</w:t>", paragraph.group(1))
        )
        if content.strip():
            lines.append(content)
    return "\n".join(lines), document_xml.count("<w:drawing")


def _html_surfaces(path: Path) -> tuple[str, str, int]:
    """Raw payload, extracted text nodes, and figure estimate of an .html file."""
    raw = path.read_text("utf-8", errors="replace")
    parser = _VisibleHtmlText()
    parser.feed(raw)
    # slideblocks draws figures as inline SVG carriers, not <img> tags.
    figures = max(raw.count("<img"), raw.count("data:image/"), raw.count("<svg"))
    return raw, parser.text(), figures


def check_report(
    *,
    text: str,
    raw_text: str | None,
    figure_count: int,
    min_figures: int,
) -> list[Finding]:
    """Run every mechanical check against the prepared surfaces.

    ``raw_text`` is the unfiltered payload (HTML only); leak checks that
    cannot false-positive on bundled code run on it too.
    """
    surfaces = [text] if raw_text is None else [text, raw_text]
    findings: list[Finding] = []

    def leaks(pattern: re.Pattern[str], check: str, label: str) -> None:
        hits: set[str] = set()
        for surface in surfaces:
            hits.update(match.group(0) for match in pattern.finditer(surface))
        findings.append(
            Finding(
                check=check,
                passed=not hits,
                detail=f"no {label}" if not hits else f"{label}: {sorted(hits)[:5]}",
            )
        )

    leaks(_PLACEHOLDER, "placeholders", "leftover placeholders")
    leaks(_INTERNAL_PATH, "internal_paths", "internal or temp paths leaked")
    leaks(_MCP_SLUG, "mcp_names", "MCP tool/server names leaked")

    dirty = [match.group(0) for match in _DIRTY_CJK.finditer(text)]
    dirty += [match.group(0) for match in _DIRTY_ASCII.finditer(text)]
    if raw_text is not None:
        dirty += [match.group(0) for match in _DIRTY_CJK.finditer(raw_text)]
    findings.append(
        Finding(
            check="draft_markers",
            passed=not dirty,
            detail="no draft markers"
            if not dirty
            else f"draft markers: {sorted(set(dirty))[:5]}",
        )
    )

    figures_ok = figure_count >= min_figures
    findings.append(
        Finding(
            check="figures",
            passed=figures_ok,
            detail=f"{figure_count} figures (required >= {min_figures})",
        )
    )

    source_lines = len(_SOURCE_LINE.findall(text))
    if raw_text is not None:
        source_lines += len(_SOURCE_LINE.findall(raw_text))
    findings.append(
        Finding(
            check="sources",
            passed=source_lines > 0,
            detail=f"{source_lines} source lines found",
        )
    )

    has_disclaimer = bool(_DISCLAIMER.search(text)) or (
        raw_text is not None and bool(_DISCLAIMER.search(raw_text))
    )
    findings.append(
        Finding(
            check="disclaimer",
            passed=has_disclaimer,
            detail="disclaimer present" if has_disclaimer else "disclaimer missing",
        )
    )

    return findings


def _check_file(path: Path, min_figures: int) -> list[Finding]:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        text, figures = _docx_surface(path)
        return check_report(
            text=text, raw_text=None, figure_count=figures, min_figures=min_figures
        )
    if suffix in {".html", ".htm"}:
        raw, text, figures = _html_surfaces(path)
        return check_report(
            text=text, raw_text=raw, figure_count=figures, min_figures=min_figures
        )
    if suffix == ".md":
        text = path.read_text("utf-8", errors="replace")
        prose = _MD_LINK.sub("()", text)
        figures = len(_MD_IMAGE.findall(text))
        return check_report(
            text=prose, raw_text=None, figure_count=figures, min_figures=min_figures
        )
    raise ValueError(f"unsupported report type: {suffix} (use .html, .docx or .md)")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Self-check a finished report before delivery."
    )
    parser.add_argument(
        "report", type=Path, help="Path to the .html / .docx / .md report"
    )
    parser.add_argument(
        "--min-figures",
        type=int,
        default=8,
        help="Minimum embedded figures (default: 8)",
    )
    args = parser.parse_args()

    if not args.report.is_file():
        print(f"FAIL report: file not found: {args.report}")
        return 1

    try:
        findings = _check_file(args.report, args.min_figures)
    except (ValueError, zipfile.BadZipFile, KeyError) as error:
        print(f"FAIL report: cannot read {args.report}: {error}")
        return 1

    for finding in findings:
        mark = "PASS" if finding.passed else "FAIL"
        print(f"{mark} {finding.check}: {finding.detail}")
    failed = [finding for finding in findings if not finding.passed]
    print(f"{'FAIL' if failed else 'PASS'} summary: {len(failed)} failed check(s)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
