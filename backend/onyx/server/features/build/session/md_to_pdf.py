"""Convert Markdown to a simple multi-page PDF using reportlab + mistune."""

from __future__ import annotations

from io import BytesIO
from typing import Any

import mistune
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
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

_HEADING_COLOR = HexColor("#0F4761")
_CODE_BG = HexColor("#F4F4F4")


def _inline_to_html(children: list[dict[str, Any]] | None) -> str:
    if not children:
        return ""
    parts: list[str] = []
    for child in children:
        kind = child.get("type")
        text = str(child.get("raw") or "")
        if kind == "text":
            parts.append(text)
        elif kind == "strong":
            parts.append(f"<b>{_inline_to_html(child.get('children'))}</b>")
        elif kind == "emphasis":
            parts.append(f"<i>{_inline_to_html(child.get('children'))}</i>")
        elif kind == "codespan":
            parts.append(f"<font face='Courier'>{text}</font>")
        elif kind == "link":
            href = str(child.get("attrs", {}).get("url") or "")
            label = _inline_to_html(child.get("children")) or href
            parts.append(f'<link href="{href}">{label}</link>')
        elif kind == "linebreak":
            parts.append("<br/>")
        else:
            parts.append(_inline_to_html(child.get("children")) or text)
    return "".join(parts)


def markdown_to_pdf_bytes(md_text: str) -> bytes:
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "MdBody",
        parent=styles["BodyText"],
        fontName="Times-Roman",
        fontSize=11,
        leading=15,
        spaceAfter=8,
    )
    heading_styles = {
        1: ParagraphStyle(
            "MdH1",
            parent=styles["Heading1"],
            textColor=_HEADING_COLOR,
            fontSize=18,
            spaceAfter=10,
        ),
        2: ParagraphStyle(
            "MdH2",
            parent=styles["Heading2"],
            textColor=_HEADING_COLOR,
            fontSize=14,
            spaceAfter=8,
        ),
        3: ParagraphStyle(
            "MdH3",
            parent=styles["Heading3"],
            textColor=_HEADING_COLOR,
            fontSize=12,
            spaceAfter=6,
        ),
    }
    code_style = ParagraphStyle(
        "MdCode",
        parent=styles["Code"],
        fontName="Courier",
        fontSize=8,
        leading=11,
        backColor=_CODE_BG,
        spaceAfter=8,
    )
    quote_style = ParagraphStyle(
        "MdQuote",
        parent=body,
        leftIndent=18,
        textColor=HexColor("#444444"),
    )

    tokens = mistune.create_markdown(renderer="ast")(md_text)
    story: list[Any] = []

    def add_blocks(nodes: list[dict[str, Any]]) -> None:
        for node in nodes:
            kind = node.get("type")
            if kind == "heading":
                level = int(node.get("attrs", {}).get("level") or 1)
                style = heading_styles.get(min(level, 3), heading_styles[3])
                story.append(Paragraph(_inline_to_html(node.get("children")), style))
            elif kind == "paragraph":
                story.append(Paragraph(_inline_to_html(node.get("children")), body))
            elif kind == "block_code":
                story.append(Preformatted(str(node.get("raw") or ""), code_style))
            elif kind == "block_quote":
                story.append(
                    Paragraph(_inline_to_html(node.get("children")), quote_style)
                )
            elif kind == "thematic_break":
                story.append(Spacer(1, 8))
            elif kind == "list":
                items: list[ListItem] = []
                for item in node.get("children") or []:
                    text = _inline_to_html(item.get("children"))
                    items.append(ListItem(Paragraph(text, body)))
                story.append(ListFlowable(items, bulletType="bullet"))
            elif kind == "table":
                rows: list[list[str]] = []
                for row in node.get("children") or []:
                    cells = [
                        _inline_to_html(cell.get("children"))
                        for cell in row.get("children") or []
                    ]
                    rows.append(cells)
                if rows:
                    table = Table(rows, hAlign="LEFT")
                    table.setStyle(
                        TableStyle(
                            [
                                ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
                                ("FONTSIZE", (0, 0), (-1, -1), 9),
                                ("GRID", (0, 0), (-1, -1), 0.25, HexColor("#CCCCCC")),
                                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                            ]
                        )
                    )
                    story.append(table)
                    story.append(Spacer(1, 8))
            else:
                children = node.get("children")
                if isinstance(children, list):
                    add_blocks(children)

    if isinstance(tokens, list):
        add_blocks(tokens)
    if not story:
        story.append(Paragraph(" ", body))

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
