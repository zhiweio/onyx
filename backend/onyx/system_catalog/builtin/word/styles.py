"""Shared visual contract for official Word report templates."""

from __future__ import annotations

from docx.document import Document as DocumentObject
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from docx.text.paragraph import Paragraph
from docx.text.run import Run

BODY_FONT = "Calibri"
BODY_EAST_ASIA = "宋体"
HEADING_FONT = "Calibri"
HEADING_EAST_ASIA = "黑体"
ACCENT = RGBColor(0x1F, 0x3A, 0x5F)


def set_run_font(
    run: Run, *, size_pt: float = 11, bold: bool = False, color: RGBColor | None = None
) -> None:
    run.font.name = BODY_FONT
    run.font.size = Pt(size_pt)
    run.bold = bold
    if color is not None:
        run.font.color.rgb = color
    r_pr = run._element.get_or_add_rPr()
    r_fonts = r_pr.get_or_add_rFonts()
    r_fonts.set(qn("w:ascii"), BODY_FONT)
    r_fonts.set(qn("w:hAnsi"), BODY_FONT)
    r_fonts.set(qn("w:eastAsia"), BODY_EAST_ASIA)


def set_heading_font(run: Run, *, size_pt: float, color: RGBColor = ACCENT) -> None:
    run.font.name = HEADING_FONT
    run.font.size = Pt(size_pt)
    run.bold = True
    run.font.color.rgb = color
    r_pr = run._element.get_or_add_rPr()
    r_fonts = r_pr.get_or_add_rFonts()
    r_fonts.set(qn("w:ascii"), HEADING_FONT)
    r_fonts.set(qn("w:hAnsi"), HEADING_FONT)
    r_fonts.set(qn("w:eastAsia"), HEADING_EAST_ASIA)


def configure_document(document: DocumentObject) -> None:
    section = document.sections[0]
    section.top_margin = Cm(2.2)
    section.bottom_margin = Cm(2.2)
    section.left_margin = Cm(2.4)
    section.right_margin = Cm(2.4)
    section.header_distance = Cm(1.0)
    section.footer_distance = Cm(1.0)

    styles = document.styles
    normal = styles["Normal"]
    normal.font.name = BODY_FONT
    normal.font.size = Pt(11)
    normal.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
    normal.paragraph_format.space_after = Pt(6)


def add_header(document: DocumentObject) -> None:
    paragraph = document.sections[0].header.paragraphs[0]
    paragraph.text = ""
    run = paragraph.add_run("{{company_header}}")
    set_run_font(run, size_pt=9, color=ACCENT)
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _add_bottom_border(paragraph)


def add_footer(document: DocumentObject) -> None:
    paragraph = document.sections[0].footer.paragraphs[0]
    paragraph.text = ""
    secret = paragraph.add_run("机密")
    set_run_font(secret, size_pt=9, color=ACCENT)
    spacer = paragraph.add_run("    ")
    set_run_font(spacer, size_pt=9)
    page_label = paragraph.add_run("第 ")
    set_run_font(page_label, size_pt=9)
    _add_page_field(paragraph)
    page_suffix = paragraph.add_run(" 页")
    set_run_font(page_suffix, size_pt=9)
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER


def add_title(document: DocumentObject, title: str) -> None:
    heading = document.add_paragraph()
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = heading.add_run(title)
    set_heading_font(run, size_pt=18)
    heading.paragraph_format.space_after = Pt(12)


def add_cover_line(document: DocumentObject) -> None:
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run(
        "主体：{{entity_name}}    期间：{{period}}    "
        "币种：{{currency}}    编制日期：{{report_date}}"
    )
    set_run_font(run, size_pt=10)
    paragraph.paragraph_format.space_after = Pt(16)


def add_heading(document: DocumentObject, text: str) -> None:
    paragraph = document.add_paragraph()
    run = paragraph.add_run(text)
    set_heading_font(run, size_pt=13)
    paragraph.paragraph_format.space_before = Pt(12)
    paragraph.paragraph_format.space_after = Pt(6)


def add_body(document: DocumentObject, text: str) -> None:
    paragraph = document.add_paragraph()
    run = paragraph.add_run(text)
    set_run_font(run, size_pt=11)


def add_bordered_table(
    document: DocumentObject,
    headers: list[str],
    prototype_cells: list[str],
) -> None:
    table = document.add_table(rows=2, cols=len(headers))
    table.style = "Table Grid"
    for index, header in enumerate(headers):
        cell = table.cell(0, index)
        cell.text = ""
        paragraph = cell.paragraphs[0]
        run = paragraph.add_run(header)
        set_run_font(run, size_pt=10, bold=True, color=RGBColor(0xFF, 0xFF, 0xFF))
        _shade_cell(cell, "1F3A5F")
    for index, token in enumerate(prototype_cells):
        cell = table.cell(1, index)
        cell.text = ""
        paragraph = cell.paragraphs[0]
        run = paragraph.add_run(token)
        set_run_font(run, size_pt=10)


def add_closing(document: DocumentObject) -> None:
    add_heading(document, "结论")
    add_body(document, "{{conclusion}}")
    add_heading(document, "未决问题")
    add_body(document, "{{open_issues}}")
    add_heading(document, "数据缺口")
    add_body(document, "{{data_gaps}}")


def _add_bottom_border(paragraph: Paragraph) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    p_bdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:space"), "4")
    bottom.set(qn("w:color"), "C5C9D0")
    p_bdr.append(bottom)
    p_pr.append(p_bdr)


def _shade_cell(cell: object, color: str) -> None:
    tc = cell._tc  # type: ignore[attr-defined]
    tc_pr = tc.get_or_add_tcPr()
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), color)
    shading.set(qn("w:val"), "clear")
    tc_pr.append(shading)


def _add_page_field(paragraph: Paragraph) -> None:
    run = paragraph.add_run()
    set_run_font(run, size_pt=9)
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(begin)
    run._r.append(instr)
    run._r.append(end)
