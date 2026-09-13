"""Convert Markdown to PDF from the shared GFM AST.

The interchange is the same mistune tree Word uses. ReportLab draws the page
with a local CJK sans when the host has one, else the built-in STSong-Light
CID font.
"""

from __future__ import annotations

from html import escape
from io import BytesIO
from typing import Any

from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    ListFlowable,
    ListItem,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus import (
    Image as RLImage,
)

from onyx.server.features.build.session.md_document import Node, parse_markdown
from onyx.server.features.build.session.md_export_style import (
    ACCENT_HEX,
    BODY_SIZE_PT,
    BODY_SPACE_AFTER_PT,
    CELL_SIZE_PT,
    CODE_BG_HEX,
    CODE_SIZE_PT,
    FOOTER_DISTANCE_MM,
    HEADER_DISTANCE_MM,
    HEADING_SIZES_PT,
    HEADING_SPACE_AFTER_PT,
    HEADING_SPACE_BEFORE_PT,
    INK_HEX,
    LINK_HEX,
    MARGIN_BOTTOM_MM,
    MARGIN_LEFT_MM,
    MARGIN_RIGHT_MM,
    MARGIN_TOP_MM,
    MUTED_HEX,
    PDF_CODE_FONT,
    RULE_HEX,
    TABLE_ALT_FILL,
    TABLE_BORDER,
    TABLE_HEADER_FILL,
    body_leading,
    cell_leading,
    first_heading_text,
    heading_leading,
    iter_script_runs,
    resolve_pdf_fonts,
    wrap_latin_html,
)
from onyx.server.features.build.session.md_images import (
    ImageLoader,
    attach_image_bytes,
    fit_image_display_size,
    image_bytes,
)


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
    latin_face: str | None = None,
    cjk_face: str | None = None,
) -> str:
    if not children:
        return ""
    fonts = resolve_pdf_fonts()
    latin = latin_face or fonts.latin
    cjk = cjk_face or fonts.body
    parts: list[str] = []
    for child in children:
        kind = child.get("type")
        raw = escape(str(child.get("raw") or ""))
        if kind == "text":
            parts.append(wrap_latin_html(raw, face=latin, cjk_face=cjk))
        elif kind == "strong":
            parts.append(
                "<b>"
                + _inline_html(
                    child.get("children"),
                    notes,
                    footnote_defs,
                    fonts.latin_bold,
                    cjk,
                )
                + "</b>"
            )
        elif kind == "emphasis":
            parts.append(
                f"<i>{_inline_html(child.get('children'), notes, footnote_defs, latin_face, cjk_face)}</i>"
            )
        elif kind == "strikethrough":
            parts.append(
                f"<strike>{_inline_html(child.get('children'), notes, footnote_defs, latin_face, cjk_face)}</strike>"
            )
        elif kind == "codespan":
            parts.append(
                "<font size='8'>"
                + wrap_latin_html(raw, face=PDF_CODE_FONT, cjk_face=cjk)
                + "</font>"
            )
        elif kind == "link":
            href = escape(str(child.get("attrs", {}).get("url") or ""), quote=True)
            label = (
                _inline_html(
                    child.get("children"),
                    notes,
                    footnote_defs,
                    latin_face,
                    cjk_face,
                )
                or href
            )
            parts.append(f'<link href="{href}" color="{LINK_HEX}">{label}</link>')
        elif kind == "image":
            if image_bytes(child) is not None:
                continue
            alt = (
                _inline_html(
                    child.get("children"),
                    notes,
                    footnote_defs,
                    latin_face,
                    cjk_face,
                )
                or "image"
            )
            parts.append(f"<i>{alt}</i>")
        elif kind in ("linebreak", "softbreak"):
            parts.append("<br/>")
        elif kind == "footnote_ref":
            def_index = int((child.get("attrs") or {}).get("index") or 0)
            notes.append(_note_html(footnote_defs.get(def_index) or []))
            parts.append(
                f"<super>{wrap_latin_html(str(len(notes)), face=latin, cjk_face=cjk)}</super>"
            )
        elif kind == "inline_html":
            continue
        else:
            parts.append(
                _inline_html(
                    child.get("children"),
                    notes,
                    footnote_defs,
                    latin_face,
                    cjk_face,
                )
                or raw
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


def markdown_to_pdf_bytes(
    md_text: str,
    *,
    image_loader: ImageLoader | None = None,
) -> bytes:
    fonts = resolve_pdf_fonts()
    nodes = parse_markdown(md_text)
    attach_image_bytes(nodes, image_loader)
    notes: list[str] = []
    footnote_defs = _footnote_defs(nodes)
    styles = _pdf_styles(fonts.body, fonts.heading)
    story: list[Any] = []
    _add_blocks(story, nodes, styles, notes, footnote_defs, list_level=0)
    if notes:
        story.append(Spacer(1, 10))
        story.append(Paragraph(wrap_latin_html("Notes"), styles["h2"]))
        for index, html in enumerate(notes, start=1):
            story.append(
                Paragraph(
                    f"<super>{wrap_latin_html(str(index))}</super> {html}",
                    styles["body"],
                )
            )
    if not story:
        story.append(Paragraph(" ", styles["body"]))

    title = first_heading_text(nodes)
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGIN_LEFT_MM * mm,
        rightMargin=MARGIN_RIGHT_MM * mm,
        topMargin=MARGIN_TOP_MM * mm,
        bottomMargin=MARGIN_BOTTOM_MM * mm,
        title=title or "Document",
    )
    document.build(
        story,
        onFirstPage=_page_chrome(fonts.body, fonts.latin, ""),
        onLaterPages=_page_chrome(fonts.body, fonts.latin, title),
    )
    return buffer.getvalue()


def _page_chrome(cjk_font: str, latin_font: str, title: str):
    def draw(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        width, height = A4
        left = MARGIN_LEFT_MM * mm
        right = width - MARGIN_RIGHT_MM * mm
        header_y = height - HEADER_DISTANCE_MM * mm
        footer_y = FOOTER_DISTANCE_MM * mm
        canvas.setStrokeColor(HexColor(RULE_HEX))
        canvas.setLineWidth(0.4)
        canvas.line(left, footer_y + 10, right, footer_y + 10)
        canvas.setFillColor(HexColor(MUTED_HEX))
        if title:
            canvas.line(left, header_y, right, header_y)
            _draw_mixed_string(
                canvas,
                left,
                header_y + 4,
                title[:40],
                cjk_font,
                latin_font,
                8,
            )
        canvas.setFont(latin_font, 8)
        canvas.drawCentredString((left + right) / 2, footer_y, f"- {doc.page} -")
        canvas.restoreState()

    return draw


def _draw_mixed_string(
    canvas: Any,
    x: float,
    y: float,
    text: str,
    cjk_font: str,
    latin_font: str,
    size: float,
) -> None:
    cursor = x
    for is_latin, chunk in iter_script_runs(text):
        font = latin_font if is_latin else cjk_font
        canvas.setFont(font, size)
        canvas.drawString(cursor, y, chunk)
        cursor += canvas.stringWidth(chunk, font, size)


def _pdf_styles(body_font: str, heading_font: str) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    ink = HexColor(INK_HEX)
    accent = HexColor(ACCENT_HEX)
    body = ParagraphStyle(
        "MdBody",
        parent=base["BodyText"],
        fontName=body_font,
        fontSize=BODY_SIZE_PT,
        leading=body_leading(),
        textColor=ink,
        spaceBefore=0,
        spaceAfter=BODY_SPACE_AFTER_PT,
    )
    styles: dict[str, ParagraphStyle] = {
        "body": body,
        "list": ParagraphStyle(
            "MdList",
            parent=body,
            spaceBefore=0,
            spaceAfter=2,
            leading=round(BODY_SIZE_PT * 1.2, 2),
        ),
        "code": ParagraphStyle(
            "MdCode",
            parent=base["Code"],
            fontName=PDF_CODE_FONT,
            fontSize=CODE_SIZE_PT,
            leading=round(CODE_SIZE_PT * 1.35, 2),
            backColor=HexColor(CODE_BG_HEX),
            textColor=ink,
            spaceBefore=4,
            spaceAfter=6,
            leftIndent=4,
            rightIndent=4,
        ),
        "quote": ParagraphStyle(
            "MdQuote",
            parent=body,
            leftIndent=10,
            rightIndent=0,
            textColor=HexColor(MUTED_HEX),
            borderPadding=4,
            leading=body_leading(),
        ),
        "caption": ParagraphStyle(
            "MdCaption",
            parent=body,
            alignment=1,
            fontSize=9,
            leading=12,
            textColor=HexColor(MUTED_HEX),
            spaceAfter=8,
        ),
        "cell": ParagraphStyle(
            "MdCell",
            parent=body,
            fontSize=CELL_SIZE_PT,
            leading=cell_leading(),
            textColor=ink,
            spaceBefore=0,
            spaceAfter=0,
        ),
        "cell_head": ParagraphStyle(
            "MdCellHead",
            parent=body,
            fontName=heading_font,
            fontSize=CELL_SIZE_PT,
            leading=cell_leading(),
            textColor=white,
            spaceBefore=0,
            spaceAfter=0,
        ),
    }
    for level, size in HEADING_SIZES_PT.items():
        styles[f"h{level}"] = ParagraphStyle(
            f"MdH{level}",
            parent=base["Heading1"] if level == 1 else base["Heading2"],
            fontName=heading_font,
            textColor=accent,
            fontSize=size,
            leading=heading_leading(level),
            spaceBefore=HEADING_SPACE_BEFORE_PT[level],
            spaceAfter=HEADING_SPACE_AFTER_PT[level],
            keepWithNext=1,
        )
    return styles


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
            level = min(int((node.get("attrs") or {}).get("level") or 1), 6)
            story.append(
                Paragraph(
                    _inline_html(
                        node.get("children"),
                        notes,
                        footnote_defs,
                        latin_face=resolve_pdf_fonts().latin_bold,
                        cjk_face=resolve_pdf_fonts().heading,
                    ),
                    styles[f"h{level}"],
                )
            )
        elif kind in ("paragraph", "block_text"):
            _add_paragraph_flowables(
                story,
                node.get("children") or [],
                styles,
                notes,
                footnote_defs,
            )
        elif kind == "block_code":
            story.append(_code_flowable(str(node.get("raw") or ""), styles["code"]))
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
            story.append(
                HRFlowable(
                    width="100%",
                    thickness=0.5,
                    color=HexColor(RULE_HEX),
                    spaceBefore=6,
                    spaceAfter=6,
                )
            )
        elif kind == "list":
            story.append(_list_flowable(node, styles, notes, footnote_defs, list_level))
        elif kind == "table":
            table = _table_flowable(node, styles, notes, footnote_defs)
            if table is not None:
                story.append(table)
                story.append(Spacer(1, 6))
        else:
            children = node.get("children")
            if isinstance(children, list):
                _add_blocks(story, children, styles, notes, footnote_defs, list_level)


def _add_paragraph_flowables(
    story: list[Any],
    children: list[Node],
    styles: dict[str, ParagraphStyle],
    notes: list[str],
    footnote_defs: dict[int, list[Node]],
) -> None:
    if _is_image_only(children):
        image = next(child for child in children if child.get("type") == "image")
        flowable = _image_flowable(image)
        if flowable is not None:
            story.append(flowable)
            alt = _collect_text(image.get("children"))
            if alt:
                story.append(Paragraph(wrap_latin_html(escape(alt)), styles["caption"]))
            return
        story.append(
            Paragraph(
                wrap_latin_html(escape(_collect_text(children) or "image")),
                styles["caption"],
            )
        )
        return

    if any(image_bytes(child) is not None for child in children):
        buffer: list[Node] = []

        def flush_text() -> None:
            if not buffer:
                return
            html = _inline_html(buffer, notes, footnote_defs)
            if html.strip():
                story.append(Paragraph(html, styles["body"]))
            buffer.clear()

        for child in children:
            if image_bytes(child) is not None:
                flush_text()
                flowable = _image_flowable(child)
                if flowable is not None:
                    story.append(flowable)
                else:
                    buffer.append(child)
            else:
                buffer.append(child)
        flush_text()
        return

    story.append(
        Paragraph(
            _inline_html(children, notes, footnote_defs),
            styles["body"],
        )
    )


def _code_flowable(raw: str, style: ParagraphStyle) -> Any:
    if not raw:
        return Preformatted(" ", style)
    if all(ord(char) < 128 for char in raw):
        return Preformatted(raw, style)
    html = wrap_latin_html(escape(raw), face=PDF_CODE_FONT)
    return Paragraph(html.replace("\n", "<br/>"), style)


def _image_flowable(node: Node) -> RLImage | None:
    data = image_bytes(node)
    if data is None:
        return None
    size = fit_image_display_size(data)
    if size is None:
        return None
    width_in, height_in = size
    try:
        image = RLImage(
            BytesIO(data),
            width=width_in * 72,
            height=height_in * 72,
        )
    except Exception:
        return None
    image.hAlign = "CENTER"
    return image


def _is_image_only(children: list[Node]) -> bool:
    meaningful = [
        child
        for child in children
        if child.get("type") not in ("softbreak", "linebreak")
        and not (
            child.get("type") == "text" and not str(child.get("raw") or "").strip()
        )
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
                        styles["list"],
                    )
                )
            elif child_type == "list":
                flowables.append(
                    _list_flowable(child, styles, notes, footnote_defs, list_level + 1)
                )
            else:
                nested: list[Any] = []
                _add_blocks(
                    nested, [child], styles, notes, footnote_defs, list_level + 1
                )
                flowables.extend(nested)
        if not flowables:
            flowables.append(Paragraph(" ", styles["list"]))
        items.append(ListItem(flowables if len(flowables) > 1 else flowables[0]))
    start = (node.get("attrs") or {}).get("start")
    if ordered:
        return ListFlowable(
            items,
            bulletType="1",
            start=int(start or 1),
            leftIndent=14 + (12 * list_level),
            bulletFontName=resolve_pdf_fonts().latin,
            spaceBefore=1,
            spaceAfter=4,
        )
    return ListFlowable(
        items,
        bulletType="bullet",
        start="l",
        leftIndent=14 + (12 * list_level),
        bulletFontName="ZapfDingbats",
        spaceBefore=1,
        spaceAfter=4,
    )


def _table_col_widths(columns: int, available: float) -> list[float]:
    """Give the label column more width than the metric columns."""
    if columns <= 1:
        return [available]
    first_share = 0.30 if columns >= 5 else 0.34
    first = available * first_share
    rest = (available - first) / (columns - 1)
    return [first] + [rest] * (columns - 1)


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
                        "<b>"
                        + _inline_html(
                            cell.get("children"),
                            notes,
                            footnote_defs,
                            latin_face=resolve_pdf_fonts().latin_bold,
                            cjk_face=resolve_pdf_fonts().heading,
                        )
                        + "</b>",
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
                            _inline_html(cell.get("children"), notes, footnote_defs),
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
    available = A4[0] - ((MARGIN_LEFT_MM + MARGIN_RIGHT_MM) * mm)
    columns = max(len(row) for row in rows)
    table = Table(
        rows,
        colWidths=_table_col_widths(columns, available),
        hAlign="LEFT",
        repeatRows=1,
    )
    commands: list[Any] = [
        ("FONTNAME", (0, 0), (-1, -1), styles["cell"].fontName),
        ("FONTSIZE", (0, 0), (-1, -1), CELL_SIZE_PT),
        ("GRID", (0, 0), (-1, -1), 0.4, HexColor(f"#{TABLE_BORDER}")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("BACKGROUND", (0, 0), (-1, 0), HexColor(f"#{TABLE_HEADER_FILL}")),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        (
            "ROWBACKGROUNDS",
            (0, 1),
            (-1, -1),
            [white, HexColor(f"#{TABLE_ALT_FILL}")],
        ),
    ]
    table.setStyle(TableStyle(commands))
    return table
