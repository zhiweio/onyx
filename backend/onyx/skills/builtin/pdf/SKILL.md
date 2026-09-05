---
name: pdf
description: Use this skill when a PDF must be read, extracted, split, merged, rotated, reordered, filled, generated, converted, or checked for scanned pages; trigger on pdf, Acrobat, form fields, OCR, pages, tables, or text extraction.
---

# PDF Skill

> **Path convention**: All commands run from the **session workspace** (your working directory). Never `cd` into the skill directory. Prefix all skill scripts with `.opencode/skills/pdf/`. All generated files (extracted JSON, text, split PDFs, filled forms, generated PDFs) go in `outputs/`.

## Quick Reference

| Task | Guide |
|------|-------|
| Extract text | `python .opencode/skills/pdf/scripts/extract_text.py --input file.pdf --format json` |
| Fill AcroForm fields | `python .opencode/skills/pdf/scripts/fill_form.py --input form.pdf --data fields.json --output outputs/filled.pdf` |
| Layout-aware extraction | Use `pdfplumber` |
| Merge, split, rotate, reorder | Use `pypdf` |
| Deep details | Read [reference.md](reference.md) |

---

## Extracting Text

Use `pypdf` for straightforward page text extraction.

```bash
python .opencode/skills/pdf/scripts/extract_text.py --input report.pdf --pages 1-3,7 --format json --output outputs/text.json
```

Use `pdfplumber` when layout matters, especially for columns, tables, coordinates, or page regions.

```python
import pdfplumber

with pdfplumber.open("report.pdf") as pdf:
    text = pdf.pages[0].extract_text()
```

## Extracting Tables

Prefer `pdfplumber` for tables. Verify the output, because table extraction depends on ruling lines, whitespace, and source PDF quality.

```python
import pdfplumber

with pdfplumber.open("report.pdf") as pdf:
    tables = [page.extract_table() for page in pdf.pages]
```

## Page Operations

Use `pypdf` to merge, split, rotate, and reorder pages.

```python
from pypdf import PdfReader, PdfWriter

reader = PdfReader("input.pdf")
writer = PdfWriter()
for index in [2, 0, 1]:
    page = reader.pages[index]
    page.rotate(90)
    writer.add_page(page)
with open("outputs/reordered.pdf", "wb") as f:
    writer.write(f)
```

## Form Fields

PDF forms can use AcroForm fields or XFA. The bundled fill script supports AcroForm fields.

```bash
python .opencode/skills/pdf/scripts/fill_form.py --input form.pdf --data fields.json --output outputs/filled.pdf
```

After filling, re-read the field values to verify the write took effect. Some viewers need appearance streams; the script sets `NeedAppearances` so viewers render the values.

## Scanned PDFs and OCR

A scanned PDF is mostly page images. Text extraction may return empty strings or junk. Do not invent missing text. Say that OCR is required, then use an OCR tool if one is available in the environment.

## Generating PDFs

For authored PDFs, write HTML or Markdown first, then convert it. This is easier to review and adjust than drawing PDF objects directly.

Common paths:

- Markdown to HTML, then browser print to PDF.
- HTML to PDF with a local renderer.
- DOCX to PDF with LibreOffice when Word-style layout is desired.

Always inspect or re-extract the generated PDF before reporting success.

## Dependencies

- `pip install pypdf` - text extraction, page operations, and AcroForm filling
- `pip install pdfplumber` - layout-aware text and table extraction
- OCR engine - required for scanned/image-only PDFs
