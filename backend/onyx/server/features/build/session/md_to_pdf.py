"""Convert Markdown to PDF from the shared GFM AST.

The interchange is the same mistune tree Word uses. ReportLab draws the page
with the built-in STSong-Light CID font so CJK does not need a shipped TTF.
"""

from __future__ import annotations

from html import escape
from io import BytesIO
from typing import Any

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from onyx.server.features.build.session.md_document import Node, parse_markdown

_HEADING_COLOR = HexColor("#0F4761")
_CODE_BG = HexColor("#F4F4F4")
_CJK_FONT = "STSong-Light"
_CODE_FONT = "Courier"

_cjk_font_registered = False


def _ensure_cjk_font() -> str:
    global _cjk_font_registered
    if not _cjk_font_registered:
        pdfmetrics.registerFont(UnicodeCIDFont(_CJK_FONT))
        _cjk_font_registered = True
    return _CJK_FONT


def _note_html(def_nodes: list[Node]) -> str:
    return " ".join(
        _inline_html(child.get("children"), [], {})
        for child in def_nodes
        if child.get("type") in ("paragraph", "block_text")
    )


def _inline_html(
    children: list[Node] | None,
    notes: list[str],
    footnote_defs: dict[int, list[Node]],
) -> str:
    if not children:
        return ""
    parts: list[str] = []
    for child in children:
        kind = child.get("type")
        raw = escape(str(child.get("raw") or ""))
        if kind == "text":
            parts.append(raw)
        elif kind == "strong":
            parts.append(
                f"<b>{_inline_html(child.get('children'), notes, footnote_defs)}</b>"
            )
        elif kind == "emphasis":
            parts.append(
                f"<i>{_inline_html(child.get('children'), notes, footnote_defs)}</i>"
            )
        elif kind == "strikethrough":
            parts.append(
                f"<strike>{_inline_html(child.get('children'), notes, footnote_defs)}</strike>"
            )
        elif kind == "codespan":
            parts.append(f"<font face='{_CODE_FONT}' size='9'>{raw}</font>")
        elif kind == "link":
            href = escape(str(child.get("attrs", {}).get("url") or ""), quote=True)
            label = (
                _inline_html(child.get("children"), notes, footnote_defs) or href
            )
            parts.append(f'<link href="{href}" color="#4F81BD">{label}</link>')
        elif kind == "image":
            alt = (
                _inline_html(child.get("children"), notes, footnote_defs) or "image"
            )
            parts.append(f"<i>{alt}</i>")
        elif kind in ("linebreak", "softbreak"):
            parts.append("<br/>")
        elif kind == "footnote_ref":
            def_index = int((child.get("attrs") or {}).get("index") or 0)
            notes.append(_note_html(footnote_defs.get(def_index) or []))
            parts.append(f"<super>{len(notes)}</super>")
        elif kind == "inline_html":
            continue
        else:
            parts.append(
                _inline_html(child.get("children"), notes, footnote_defs) or raw
            )
    return "".join(parts)


def _collect_text(children: list[Node] | None) -> str:
    if not children:
        return ""
    parts: list[str] = []
    for child in children:
        if child.get("type") == "text":
            parts.append(str(child.get("raw") or ""))
        else:
            parts.append(_collect_text(child.get("children")))
    return "".join(parts)


def _footnote_defs(nodes: list[Node]) -> dict[int, list[Node]]:
    defs: dict[int, list[Node]] = {}
    for node in nodes:
        if node.get("type") != "footnotes":
            continue
        for item in node.get("children") or []:
            index = int((item.get("attrs") or {}).get("index") or 0)
            if index:
                defs[index] = item.get("children") or []
    return defs


def markdown_to_pdf_bytes(md_text: str) -> bytes:
    cjk_font = _ensure_cjk_font()
    nodes = parse_markdown(md_text)
    notes: list[str] = []
    footnote_defs = _footnote_defs(nodes)
    styles = _pdf_styles(cjk_font)
    story: list[Any] = []
    _add_blocks(story, nodes, styles, notes, footnote_defs, list_level=0)
    if notes:
        story.append(Spacer(1, 12))
        story.append(Paragraph("Notes", styles["h2"]))
        for index, html in enumerate(notes, start=1):
            story.append(
                Paragraph(f"<super>{index}</super> {html}", styles["body"])
            )
    if not story:
        story.append(Paragraph(" ", styles["body"]))

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=inch,
        rightMargin=inch,
        topMargin=inch,
        bottomMargin=inch,
    )
    document.build(story)
    return buffer.getvalue()


def _pdf_styles(cjk_font: str) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    body = ParagraphStyle(
        "MdBody",
        parent=base["BodyText"],
        fontName=cjk_font,
        fontSize=12,
        leading=17,
        spaceAfter=8,
    )
    return {
        "body": body,
        "h1": ParagraphStyle(
            "MdH1",
            parent=base["Heading1"],
            fontName=cjk_font,
            textColor=_HEADING_COLOR,
            fontSize=20,
            leading=24,
            spaceAfter=10,
            spaceBefore=4,
        ),
        "h2": ParagraphStyle(
            "MdH2",
            parent=base["Heading2"],
            fontName=cjk_font,
            textColor=_HEADING_COLOR,
            fontSize=16,
            leading=20,
            spaceAfter=8,
        ),
        "h3": ParagraphStyle(
            "MdH3",
            parent=base["Heading3"],
            fontName=cjk_font,
            textColor=_HEADING_COLOR,
            fontSize=14,
            leading=18,
            spaceAfter=6,
        ),
        "code": ParagraphStyle(
            "MdCode",
            parent=base["Code"],
            fontName=_CODE_FONT,
            fontSize=8,
            leading=11,
            backColor=_CODE_BG,
            spaceAfter=8,
        ),
        "quote": ParagraphStyle(
            "MdQuote",
            parent=body,
            leftIndent=24,
            rightIndent=24,
            textColor=HexColor("#444444"),
        ),
        "caption": ParagraphStyle(
            "MdCaption",
            parent=body,
            alignment=1,
            textColor=HexColor("#555555"),
        ),
        "cell": ParagraphStyle(
            "MdCell",
            parent=body,
            fontSize=9,
            leading=12,
            spaceAfter=0,
        ),
        "cell_head": ParagraphStyle(
            "MdCellHead",
            parent=body,
            fontSize=9,
            leading=12,
            spaceAfter=0,
        ),
    }


def _add_blocks(
    story: list[Any],
    nodes: list[Node],
    styles: dict[str, ParagraphStyle],
    notes: list[str],
    footnote_defs: dict[int, list[Node]],
    list_level: int,
) -> None:
    for node in nodes:
        kind = node.get("type")
        if kind in ("blank_line", "newline", "footnotes"):
            continue
        if kind == "heading":
            level = min(int((node.get("attrs") or {}).get("level") or 1), 3)
            key = f"h{level}"
            story.append(
                Paragraph(
                    _inline_html(node.get("children"), notes, footnote_defs),
                    styles[key],
                )
            )
        elif kind in ("paragraph", "block_text"):
            if _is_image_only(node.get("children") or []):
                alt = _collect_text(node.get("children")) or "image"
                story.append(Paragraph(escape(alt), styles["caption"]))
            else:
                story.append(
                    Paragraph(
                        _inline_html(node.get("children"), notes, footnote_defs),
                        styles["body"],
                    )
                )
        elif kind == "block_code":
            story.append(Preformatted(str(node.get("raw") or ""), styles["code"]))
        elif kind == "block_quote":
            for child in node.get("children") or []:
                if child.get("type") in ("paragraph", "block_text"):
                    story.append(
                        Paragraph(
                            _inline_html(child.get("children"), notes, footnote_defs),
                            styles["quote"],
                        )
                    )
                else:
                    _add_blocks(
                        story,
                        [child],
                        styles,
                        notes,
                        footnote_defs,
                        list_level,
                    )
        elif kind == "thematic_break":
            story.append(Spacer(1, 10))
        elif kind == "list":
            story.append(
                _list_flowable(node, styles, notes, footnote_defs, list_level)
            )
        elif kind == "table":
            table = _table_flowable(node, styles, notes, footnote_defs)
            if table is not None:
                story.append(table)
                story.append(Spacer(1, 8))
        else:
            children = node.get("children")
            if isinstance(children, list):
                _add_blocks(story, children, styles, notes, footnote_defs, list_level)


def _is_image_only(children: list[Node]) -> bool:
    meaningful = [
        child
        for child in children
        if child.get("type") not in ("softbreak", "linebreak")
        and not (child.get("type") == "text" and not str(child.get("raw") or "").strip())
    ]
    return len(meaningful) == 1 and meaningful[0].get("type") == "image"


def _list_flowable(
    node: Node,
    styles: dict[str, ParagraphStyle],
    notes: list[str],
    footnote_defs: dict[int, list[Node]],
    list_level: int,
) -> ListFlowable:
    ordered = bool((node.get("attrs") or {}).get("ordered"))
    items: list[ListItem] = []
    for item in node.get("children") or []:
        if item.get("type") != "list_item":
            continue
        flowables: list[Any] = []
        for child in item.get("children") or []:
            child_type = child.get("type")
            if child_type in ("blank_line", "newline"):
                continue
            if child_type in ("paragraph", "block_text"):
                flowables.append(
                    Paragraph(
                        _inline_html(child.get("children"), notes, footnote_defs),
                        styles["body"],
                    )
                )
            elif child_type == "list":
                flowables.append(
                    _list_flowable(
                        child, styles, notes, footnote_defs, list_level + 1
                    )
                )
            else:
                nested: list[Any] = []
                _add_blocks(
                    nested, [child], styles, notes, footnote_defs, list_level + 1
                )
                flowables.extend(nested)
        if not flowables:
            flowables.append(Paragraph(" ", styles["body"]))
        items.append(ListItem(flowables if len(flowables) > 1 else flowables[0]))
    start = (node.get("attrs") or {}).get("start")
    return ListFlowable(
        items,
        bulletType="1" if ordered else "bullet",
        start=int(start or 1) if ordered else None,
        leftIndent=18 + (18 * list_level),
    )


def _table_flowable(
    node: Node,
    styles: dict[str, ParagraphStyle],
    notes: list[str],
    footnote_defs: dict[int, list[Node]],
) -> Table | None:
    rows: list[list[Paragraph]] = []
    for child in node.get("children") or []:
        kind = child.get("type")
        if kind == "table_head":
            rows.append(
                [
                    Paragraph(
                        f"<b>{_inline_html(cell.get('children'), notes, footnote_defs)}</b>",
                        styles["cell_head"],
                    )
                    for cell in child.get("children") or []
                    if cell.get("type") == "table_cell"
                ]
            )
        elif kind == "table_body":
            for row in child.get("children") or []:
                if row.get("type") != "table_row":
                    continue
                rows.append(
                    [
                        Paragraph(
                            _inline_html(
                                cell.get("children"), notes, footnote_defs
                            ),
                            styles["cell"],
                        )
                        for cell in row.get("children") or []
                        if cell.get("type") == "table_cell"
                    ]
                )
        elif kind == "table_row":
            rows.append(
                [
                    Paragraph(
                        _inline_html(cell.get("children"), notes, footnote_defs),
                        styles["cell"],
                    )
                    for cell in child.get("children") or []
                    if cell.get("type") == "table_cell"
                ]
            )
    if not rows:
        return None
    table = Table(rows, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), _CJK_FONT),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.25, HexColor("#CCCCCC")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("BACKGROUND", (0, 0), (-1, 0), HexColor("#F7F7F7")),
            ]
        )
    )
    return table
