"""Shared report typography for Markdown → DOCX / PDF / print HTML.

The values follow compact research-note practice (A4, 10.5pt body, 1.15
leading, navy hierarchy, full-width tables) rather than a loose letter page.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont

Node = dict[str, Any]

# Ink / chrome — compact research-note palette (A4 sans, ink type, hairline tables).
ACCENT = "185FA5"
ACCENT_HEX = "#185FA5"
INK = "1D2939"
INK_HEX = "#1D2939"
MUTED = "667085"
MUTED_HEX = "#667085"
RULE = "D0D5DD"
RULE_HEX = "#D0D5DD"
TABLE_HEADER_FILL = "185FA5"
TABLE_ALT_FILL = "F4F6F8"
TABLE_BORDER = "D0D5DD"
CODE_BG = "F2F4F7"
CODE_BG_HEX = "#F2F4F7"
LINK = "2B6CB0"
LINK_HEX = "#2B6CB0"
WHITE = "FFFFFF"

BODY_FONT = "Calibri"
BODY_EAST_ASIA = "微软雅黑"
HEADING_FONT = "Calibri"
HEADING_EAST_ASIA = "黑体"
MONO_FONT = "Courier New"

BODY_SIZE_PT = 10.5
HEADING_SIZES_PT = {1: 16.0, 2: 13.0, 3: 11.5, 4: 11.0, 5: 10.5, 6: 10.5}
HEADING_SPACE_BEFORE_PT = {1: 6.0, 2: 9.0, 3: 8.0, 4: 6.0, 5: 6.0, 6: 6.0}
HEADING_SPACE_AFTER_PT = {1: 4.0, 2: 3.0, 3: 2.5, 4: 2.0, 5: 2.0, 6: 2.0}
CODE_SIZE_PT = 8.5
CELL_SIZE_PT = 9.0
CAPTION_SIZE_PT = 9.0
CHROME_SIZE_PT = 8.0

# 1.15 is the PDF / print-HTML multiple. Word cannot use the same "auto"
# multiple: it multiplies 微软雅黑's tall line box and reads as ~1.5–1.8.
BODY_LINE_SPACING = 1.15
COMPACT_LINE_SPACING = 1.1
CELL_LINE_SPACING = 1.1
HEADING_LINE_SPACING = 1.15
CODE_LINE_SPACING = 1.2
BODY_SPACE_AFTER_PT = 3.5
COMPACT_SPACE_PT = 0.5
BLOCK_SPACE_PT = 3.0
BLOCK_INDENT_IN = 0.18

# 10.5pt × 1.15 = 12.075pt ≈ 242 twips. Hint only; do not snap to this grid.
DOC_GRID_LINE_PITCH = "242"

PAGE_WIDTH_MM = 210.0
PAGE_HEIGHT_MM = 297.0
MARGIN_LEFT_MM = 18.0
MARGIN_RIGHT_MM = 18.0
MARGIN_TOP_MM = 16.0
MARGIN_BOTTOM_MM = 16.0
HEADER_DISTANCE_MM = 8.0
FOOTER_DISTANCE_MM = 8.0

# ReportLab always has this CID face. Use it when no TTF/OTF is on the host.
_CID_FALLBACK = "STSong-Light"

_REGULAR_FONT_PATHS = (
    "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJKsc-Regular.otf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto-cjk/NotoSansCJKsc-Regular.otf",
    "/usr/share/fonts/opentype/noto-cjk/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
)

_BOLD_FONT_PATHS = (
    "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Bold.otf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJKsc-Bold.otf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto-cjk/NotoSansCJKsc-Bold.otf",
    "/System/Library/Fonts/STHeiti Medium.ttc",
)

# Noto CJK TTC: 0 JP, 1 KR, 2 SC. Other collections use the first face.
_NOTO_CJK_INDEXES = (2, 0, 1)
_DEFAULT_TTC_INDEXES = (0, 1, 2)

PDF_BODY_FONT = "CraftCJK"
PDF_HEADING_FONT = "CraftCJK-Bold"
PDF_LATIN_FONT = "CraftLatin"
PDF_LATIN_BOLD_FONT = "CraftLatin-Bold"
PDF_CODE_FONT = "Courier"
_HELVETICA = "Helvetica"
_HELVETICA_BOLD = "Helvetica-Bold"

# ASCII letters and digits look wrong in CJK faces. Keep those runs on a
# Western sans (Helvetica, or Arial / Liberation when the host has one).
_LATIN_RUN = re.compile(r"[\x20-\x7E]+")

_LATIN_REGULAR_PATHS = (
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
)
_LATIN_BOLD_PATHS = (
    "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
)


@dataclass(frozen=True)
class PdfFonts:
    body: str
    heading: str
    latin: str
    latin_bold: str
    marker: str


_pdf_fonts: PdfFonts | None = None


def first_heading_text(nodes: list[Node]) -> str:
    """Return the first heading as plain text, or an empty string."""
    for node in nodes:
        if node.get("type") == "heading":
            return collect_plain_text(node.get("children") or []).strip()
        children = node.get("children")
        if isinstance(children, list):
            nested = first_heading_text(children)
            if nested:
                return nested
    return ""


def collect_plain_text(nodes: list[Node]) -> str:
    parts: list[str] = []
    for node in nodes:
        if node.get("type") == "text":
            parts.append(str(node.get("raw") or ""))
        elif node.get("children"):
            parts.append(collect_plain_text(node["children"]))
        elif "raw" in node:
            parts.append(str(node.get("raw") or ""))
    return "".join(parts)


def heading_leading(level: int) -> float:
    size = HEADING_SIZES_PT.get(level, HEADING_SIZES_PT[3])
    return round(size * HEADING_LINE_SPACING, 2)


def body_leading() -> float:
    return round(BODY_SIZE_PT * BODY_LINE_SPACING, 2)


def cell_leading() -> float:
    return round(CELL_SIZE_PT * CELL_LINE_SPACING, 2)


def word_exact_line_pt(size_pt: float, multiple: float, extra_pt: float = 3.5) -> float:
    """Fixed Word line height in points.

    ``lineRule=auto`` times a CJK face is taller than ``size × multiple``.
    Exact leading matches the PDF more closely and avoids clipping 微软雅黑.
    """
    return round(max(size_pt * multiple, size_pt + extra_pt), 1)


def word_heading_line_pt(level: int) -> float:
    size = HEADING_SIZES_PT.get(level, HEADING_SIZES_PT[3])
    return word_exact_line_pt(size, HEADING_LINE_SPACING)


WORD_BODY_LINE_PT = word_exact_line_pt(BODY_SIZE_PT, BODY_LINE_SPACING)
WORD_COMPACT_LINE_PT = word_exact_line_pt(
    BODY_SIZE_PT, COMPACT_LINE_SPACING, extra_pt=2.5
)
WORD_CELL_LINE_PT = word_exact_line_pt(CELL_SIZE_PT, CELL_LINE_SPACING, extra_pt=2.5)
WORD_CODE_LINE_PT = word_exact_line_pt(CODE_SIZE_PT, CODE_LINE_SPACING, extra_pt=2.5)


def iter_script_runs(text: str) -> list[tuple[bool, str]]:
    """Split mixed text into (is_latin, chunk) runs for PDF drawing."""
    if not text:
        return []
    runs: list[tuple[bool, str]] = []
    last = 0
    for match in _LATIN_RUN.finditer(text):
        if match.start() > last:
            runs.append((False, text[last : match.start()]))
        prefix, core, suffix = _split_latin_chunk(match.group(0))
        if prefix:
            runs.append((False, prefix))
        if core:
            runs.append((True, core))
        if suffix:
            runs.append((False, suffix))
        last = match.end()
    if last < len(text):
        runs.append((False, text[last:]))
    return runs


def wrap_latin_html(
    text: str,
    face: str | None = None,
    cjk_face: str | None = None,
) -> str:
    """Mark Latin and CJK runs so ReportLab does not keep the last face."""
    if not text:
        return ""
    fonts = resolve_pdf_fonts()
    latin = face or fonts.latin
    cjk = cjk_face or fonts.body
    parts: list[str] = []
    for is_latin, chunk in iter_script_runs(text):
        name = latin if is_latin else cjk
        parts.append(f'<font name="{name}">{chunk}</font>')
    return "".join(parts)


def resolve_pdf_fonts() -> PdfFonts:
    """Register CJK and Latin faces for ReportLab."""
    global _pdf_fonts
    if _pdf_fonts is not None:
        return _pdf_fonts

    latin, latin_bold = _resolve_latin_fonts()
    regular = _register_first(PDF_BODY_FONT, _REGULAR_FONT_PATHS)
    if regular is None:
        pdfmetrics.registerFont(UnicodeCIDFont(_CID_FALLBACK))
        _pdf_fonts = PdfFonts(
            body=_CID_FALLBACK,
            heading=_CID_FALLBACK,
            latin=latin,
            latin_bold=latin_bold,
            marker="STSong",
        )
        return _pdf_fonts

    bold = _register_first(PDF_HEADING_FONT, _BOLD_FONT_PATHS)
    heading = PDF_HEADING_FONT if bold is not None else PDF_BODY_FONT
    try:
        pdfmetrics.registerFontFamily(
            PDF_BODY_FONT,
            normal=PDF_BODY_FONT,
            bold=heading,
            italic=PDF_BODY_FONT,
            boldItalic=heading,
        )
    except Exception:
        pass
    _pdf_fonts = PdfFonts(
        body=PDF_BODY_FONT,
        heading=heading,
        latin=latin,
        latin_bold=latin_bold,
        marker=PDF_BODY_FONT,
    )
    return _pdf_fonts


def _resolve_latin_fonts() -> tuple[str, str]:
    regular = _register_first(PDF_LATIN_FONT, _LATIN_REGULAR_PATHS)
    if regular is None:
        return _HELVETICA, _HELVETICA_BOLD
    bold = _register_first(PDF_LATIN_BOLD_FONT, _LATIN_BOLD_PATHS)
    latin_bold = PDF_LATIN_BOLD_FONT if bold is not None else PDF_LATIN_FONT
    try:
        pdfmetrics.registerFontFamily(
            PDF_LATIN_FONT,
            normal=PDF_LATIN_FONT,
            bold=latin_bold,
            italic=PDF_LATIN_FONT,
            boldItalic=latin_bold,
        )
    except Exception:
        pass
    return PDF_LATIN_FONT, latin_bold


def print_css() -> str:
    """CSS for the print-HTML interchange (WeasyPrint / Chromium)."""
    h_rules = "\n".join(
        f"  h{level} {{"
        f" font-size: {size}pt;"
        f" margin-top: {HEADING_SPACE_BEFORE_PT[level]}pt;"
        f" margin-bottom: {HEADING_SPACE_AFTER_PT[level]}pt;"
        f" }}"
        for level, size in HEADING_SIZES_PT.items()
    )
    return f"""
  @page {{
    size: A4;
    margin: {MARGIN_TOP_MM}mm {MARGIN_RIGHT_MM}mm {MARGIN_BOTTOM_MM}mm {MARGIN_LEFT_MM}mm;
  }}
  body {{
    font-family: "{BODY_FONT}", Helvetica, Arial, "Liberation Sans", "{BODY_EAST_ASIA}", "WenQuanYi Zen Hei", "Noto Sans CJK SC", sans-serif;
    font-size: {BODY_SIZE_PT}pt;
    line-height: {BODY_LINE_SPACING};
    color: {INK_HEX};
  }}
  h1, h2, h3, h4, h5, h6 {{
    color: {ACCENT_HEX};
    font-family: "{HEADING_FONT}", Helvetica, Arial, "Liberation Sans", "{HEADING_EAST_ASIA}", "WenQuanYi Zen Hei", "Noto Sans CJK SC", sans-serif;
    font-weight: 700;
    line-height: {HEADING_LINE_SPACING};
  }}
{h_rules}
  p {{ margin: 0 0 {BODY_SPACE_AFTER_PT}pt 0; }}
  pre, code {{ font-family: "{MONO_FONT}", Courier, monospace; }}
  pre {{
    background: {CODE_BG_HEX};
    padding: 6pt 8pt;
    font-size: {CODE_SIZE_PT}pt;
    line-height: {CODE_LINE_SPACING};
  }}
  blockquote {{
    margin: {BLOCK_SPACE_PT}pt 0;
    padding-left: 10pt;
    border-left: 2pt solid {ACCENT_HEX};
    color: {MUTED_HEX};
  }}
  table {{
    border-collapse: collapse;
    width: 100%;
    font-size: {CELL_SIZE_PT}pt;
    line-height: {CELL_LINE_SPACING};
  }}
  th, td {{
    border: 0.4pt solid {RULE_HEX};
    padding: 3pt 5pt;
    vertical-align: middle;
  }}
  th {{
    background: {ACCENT_HEX};
    color: #{WHITE};
    font-weight: 700;
  }}
  tr:nth-child(even) td {{ background: #{TABLE_ALT_FILL}; }}
  a {{ color: {LINK_HEX}; text-decoration: none; }}
  hr {{ border: 0; border-top: 0.5pt solid {RULE_HEX}; }}
"""


def print_html_document(body: str) -> str:
    return (
        "<!DOCTYPE html>\n"
        '<html lang="zh-CN">\n'
        "<head>\n"
        '<meta charset="utf-8"/>\n'
        "<title>Document</title>\n"
        f"<style>{print_css()}</style>\n"
        "</head>\n"
        f"<body>\n{body}\n</body>\n"
        "</html>\n"
    )


def _split_latin_chunk(chunk: str) -> tuple[str, str, str]:
    if not any(char.isalnum() for char in chunk):
        return chunk, "", ""
    core = chunk.strip()
    start = chunk.find(core)
    return chunk[:start], core, chunk[start + len(core) :]


def _ttc_indexes(path: str) -> tuple[int, ...]:
    lowered = path.lower().replace("-", "")
    if "notosanscjk" in lowered or "notocjk" in lowered:
        return _NOTO_CJK_INDEXES
    return _DEFAULT_TTC_INDEXES


def _register_first(name: str, paths: tuple[str, ...]) -> str | None:
    for path in paths:
        if not Path(path).is_file():
            continue
        suffix = path.lower()
        if suffix.endswith((".ttc", ".otc")):
            indexes = _ttc_indexes(path)
        else:
            indexes = (0,)
        for index in indexes:
            if _register_face(name, path, index):
                return path
    return None


def _register_face(name: str, path: str, index: int) -> bool:
    try:
        pdfmetrics.registerFont(TTFont(name, path, subfontIndex=index))
        return True
    except Exception:
        try:
            pdfmetrics.registerFont(TTFont(name, path))
            return True
        except Exception:
            return False
