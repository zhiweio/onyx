"""Locate and extract the key sections of an A-share annual report PDF.

年报（沪深主板）是标准十节结构。脚本用 pypdf 读书签定位，无书签时扫描页首行
「第X节」标题兜底，输出各节文本与 manifest（页码范围、审计意见类型）::

    python extract_annual_report.py --pdf attachments/雪龙集团2024.pdf \
        --year 2024 --out outputs/analysis [--tables]

输出::

    <out>/annual_<year>/summary.txt         第二节 公司简介和主要财务指标
    <out>/annual_<year>/mdna.txt            第三节 管理层讨论与分析
    <out>/annual_<year>/governance.txt      第四节 公司治理
    <out>/annual_<year>/important.txt       第六节 重要事项
    <out>/annual_<year>/financial_report.txt 第十节 财务报告（含审计报告）
    <out>/annual_<year>/manifest.json       页码范围与审计意见

``--tables`` 对定位页用 pdfplumber 抽表格（未安装则跳过并提示）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# 节 id → 标题匹配模式（匹配书签标题或页首行）
SECTION_PATTERNS: dict[str, str] = {
    "summary": r"公司简介和主要财务指标",
    "mdna": r"管理层讨论与分析|管理层讨论",
    "governance": r"^公司治理|公司治理$|第\s*四\s*节",
    "important": r"重要事项",
    "financial_report": r"^财务报告$|第十节|财务报告",
}

AUDIT_OPINIONS: tuple[str, ...] = (
    "标准无保留意见",
    "带强调事项段的无保留意见",
    "保留意见",
    "无法表示意见",
    "否定意见",
)

_SECTION_LINE = re.compile(r"^\s*第\s*([一二三四五六七八九十]+)\s*节\s*(.*)")
# Only「第X节」titles count as section boundaries — the financial-statement
# notes reuse names like 重要事项 and must not trigger a section match.
_SECTION_HEADING = re.compile(r"^第\s*[一二三四五六七八九十]+\s*节")


def match_section(title: str) -> str | None:
    """Map an outline/heading title to a section id, else None."""
    cleaned = title.strip()
    for section_id, pattern in SECTION_PATTERNS.items():
        if re.search(pattern, cleaned):
            return section_id
    return None


def detect_audit_opinion(text: str) -> str | None:
    # PDF extraction inserts spaces between glyphs; compact before matching.
    compact = re.sub(r"\s+", "", text)
    # 「非无保留意见」是审计责任段的模板句，不是意见类型本身。
    compact = compact.replace("非无保留意见", "")
    for opinion in AUDIT_OPINIONS:
        if opinion in compact:
            return opinion
    return None


def _flatten_outline(reader: object) -> list[tuple[str, int]]:
    """Yield (title, 1-based page) for every top-level outline entry."""
    pages: list[tuple[str, int]] = []
    try:
        outline = reader.outline  # type: ignore[attr-defined]
    except Exception:
        return pages

    def walk(items: list[object]) -> None:
        for item in items:
            if isinstance(item, list):
                walk(item)
                continue
            try:
                title = str(item.title)  # type: ignore[attr-defined]
                page = reader.get_destination_page_number(item) + 1  # type: ignore[attr-defined]
            except Exception:
                continue
            pages.append((title, page))

    walk(list(outline))
    return pages


def _scan_page_tops(reader: object) -> list[tuple[str, int]]:
    """Fallback: scan each page's first non-empty lines for 第X节 headings."""
    found: list[tuple[str, int]] = []
    try:
        iterator = reader.pages  # type: ignore[attr-defined]
    except Exception:
        return found
    for index, page in enumerate(iterator):
        try:
            text = page.extract_text() or ""  # type: ignore[attr-defined]
        except Exception:
            continue
        for line in text.splitlines()[:8]:
            if _SECTION_LINE.match(line):
                found.append((line.strip(), index + 1))
                break
    return found


def locate_sections(
    entries: list[tuple[str, int]], total_pages: int
) -> dict[str, tuple[int, int]]:
    """Collapse (title, page) entries into 1-based inclusive section ranges."""
    located: list[tuple[str, int, int]] = []
    for title, page in entries:
        if not _SECTION_HEADING.match(re.sub(r"\s+", "", title)):
            continue
        section_id = match_section(title)
        if section_id is None:
            continue
        if all(existing[0] != section_id for existing in located):
            located.append((section_id, page, len(located)))
    located.sort(key=lambda item: item[1])
    ranges: dict[str, tuple[int, int]] = {}
    for position, (section_id, start, _) in enumerate(located):
        if position + 1 < len(located):
            end = located[position + 1][1] - 1
        else:
            end = total_pages
        ranges[section_id] = (start, max(start, end))
    return ranges


def extract(pdf_path: Path, out_dir: Path, tables: bool) -> dict[str, object]:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    total_pages = len(reader.pages)
    entries = _flatten_outline(reader)
    if not entries:
        entries = _scan_page_tops(reader)
    ranges = locate_sections(entries, total_pages)
    if not ranges:
        raise SystemExit(
            "未定位到任何年报章节：PDF 可能是扫描件或非标准十节结构。"
            "请人工核对目录页码后改用 pdftotext -layout 分段提取。"
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {
        "pdf": str(pdf_path),
        "total_pages": total_pages,
        "sections": {},
        "audit_opinion": None,
    }
    financial_text = ""
    for section_id, (start, end) in sorted(ranges.items()):
        chunks: list[str] = []
        for index in range(start - 1, min(end, total_pages)):
            try:
                chunks.append(reader.pages[index].extract_text() or "")
            except Exception as error:  # noqa: PERF203 - per-page resilience
                chunks.append(f"[page {index + 1} extract error: {error}]")
        text = "\n".join(chunks)
        if section_id == "financial_report":
            financial_text = text
        (out_dir / f"{section_id}.txt").write_text(text, encoding="utf-8")
        section_manifest: dict[str, object] = {"start": start, "end": end}
        manifest["sections"][section_id] = section_manifest  # type: ignore[index]

    # 意见类型的权威声明在首页「重要提示」；第十节只有审计报告正文。
    front_text = "".join(
        reader.pages[index].extract_text() or "" for index in range(min(3, total_pages))
    )
    opinion = detect_audit_opinion(front_text + financial_text)
    manifest["audit_opinion"] = opinion
    if financial_text:
        financial_manifest = manifest["sections"]["financial_report"]
        assert isinstance(financial_manifest, dict)
        financial_manifest["audit_opinion"] = opinion

    if tables:
        try:
            import pdfplumber
        except ImportError:
            print("pdfplumber 未安装，跳过表格抽取", file=sys.stderr)
        else:
            tables_path = out_dir / "tables.txt"
            blocks: list[str] = []
            with pdfplumber.open(str(pdf_path)) as document:
                for section_id, (start, end) in sorted(ranges.items()):
                    for index in range(start - 1, min(end, len(document.pages))):
                        page_tables = document.pages[index].extract_tables()
                        blocks.extend(
                            f"== {section_id} p.{index + 1} ==\n"
                            + "\n".join(
                                " | ".join("" if c is None else str(c) for c in row)
                                for row in table
                            )
                            for table in page_tables
                        )
            tables_path.write_text("\n\n".join(blocks), encoding="utf-8")
            manifest["tables"] = str(tables_path)  # type: ignore[assignment]

    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def _self_test() -> int:
    checks: tuple[tuple[object, object], ...] = (
        (match_section("第二节 公司简介和主要财务指标"), "summary"),
        (match_section("第三节 管理层讨论与分析"), "mdna"),
        (match_section("第十节 财务报告"), "financial_report"),
        (match_section("目录"), None),
        (
            detect_audit_opinion("本公司出具的审计意见为标准无保留意见"),
            "标准无保留意见",
        ),
        (detect_audit_opinion("营业收入保持增长"), None),
    )
    for actual, expected in checks:
        if actual != expected:
            print(f"self-test failed: {actual!r} != {expected!r}", file=sys.stderr)
            return 1
    print("self-test passed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pdf", type=Path, help="年报 PDF 路径")
    parser.add_argument("--year", type=int, help="报告年度，如 2024")
    parser.add_argument("--out", type=Path, default=Path("outputs/analysis"))
    parser.add_argument("--tables", action="store_true", help="用 pdfplumber 抽表格")
    parser.add_argument(
        "--self-test", action="store_true", help="校验章节匹配与审计意见识别"
    )
    args = parser.parse_args()

    if args.self_test:
        return _self_test()
    if not args.pdf or not args.year:
        parser.error("需要 --pdf 与 --year，或使用 --self-test")
        return 2

    out_dir = args.out / f"annual_{args.year}"
    manifest = extract(args.pdf, out_dir, args.tables)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
