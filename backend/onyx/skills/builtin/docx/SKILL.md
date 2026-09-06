---
name: docx
description: Use this skill when a Word .docx document must be created, read, edited, templated, inspected for comments or tracked changes, or converted to PDF; trigger on docx, Word, document, template, comments, redlines, tracked changes, or placeholders.
---

# DOCX Skill

> **Path convention**: All commands run from the **session workspace** (your working directory). Never `cd` into the skill directory. Prefix all skill scripts with `.opencode/skills/docx/`. All generated files (filled documents, unpacked dirs, PDFs, extracted JSON) go in `outputs/`.

## Quick Reference

| Task | Guide |
|------|-------|
| Create or edit a document | Use `python-docx` |
| Fill a template | `python .opencode/skills/docx/scripts/fill_template.py --template template.docx --data data.json --output outputs/filled.docx` |
| Read comments and tracked changes | `python .opencode/skills/docx/scripts/read_comments.py --input document.docx --output outputs/review.json` |
| Inspect package XML | Read [reference.md](reference.md) |
| Convert to PDF | `soffice --headless --convert-to pdf --outdir outputs document.docx` |

---

## Creating Documents

Use `python-docx` for normal Word documents. Create the document, add content in order, then save to `outputs/<name>.docx`.

```python
from docx import Document

doc = Document()
doc.add_heading("Quarterly Brief", level=1)
doc.add_paragraph("This paragraph uses the default body style.")
para = doc.add_paragraph()
run = para.add_run("Important: ")
run.bold = True
para.add_run("review the final figures before sending.")
doc.save("outputs/brief.docx")
```

## Text, Runs, and Formatting

A paragraph contains runs. A run is a span that shares character formatting.

- Use paragraph styles for document-level consistency.
- Use run formatting for local emphasis such as bold, italic, underline, color, and font size.
- Do not replace `paragraph.text` when you must preserve formatting. That rewrites the paragraph runs.
- For placeholders, replace text inside the existing runs when possible.

## Tables

Use tables for structured content.

```python
table = doc.add_table(rows=1, cols=3)
table.style = "Table Grid"
headers = ["Item", "Owner", "Status"]
for cell, text in zip(table.rows[0].cells, headers, strict=True):
    cell.text = text
row = table.add_row().cells
row[0].text = "Risk review"
row[1].text = "Finance"
row[2].text = "Open"
```

For styled text inside a cell, clear the cell paragraph and add runs instead of assigning `cell.text`.

## Page Breaks and Sections

Use `doc.add_page_break()` for a hard page break. Use sections when margins, orientation, headers, or footers must change.

```python
from docx.enum.section import WD_SECTION
from docx.enum.section import WD_ORIENT

section = doc.add_section(WD_SECTION.NEW_PAGE)
section.orientation = WD_ORIENT.LANDSCAPE
section.page_width, section.page_height = section.page_height, section.page_width
```

## Filling Official Report Templates

When `SCENARIO.md` names a Word template, fill that file. Do not rewrite the
template. Do not invent a parallel markdown report.

The official contract:

- Tokens are `{{name}}`. Names come from the file. Typed metadata (kind,
  required, description) is listed in `SCENARIO.md`.
- Scalar tokens take a string, number, or date.
- A table row that contains `{{findings.title}}`, `{{findings.severity}}`, …
  is a **prototype row**. In JSON, `findings` is an array of objects. The
  script clones that row once per item.
- After fill, leftover `{{…}}` tokens fail the run (non-zero exit). Unused
  JSON keys are reported and are not fatal.
- Missing evidence still needs a value: write `未获取` or `N/A`.

```json
{
  "entity_name": "某某股份有限公司",
  "period": "2026年8月",
  "currency": "CNY",
  "report_date": "2026-09-05",
  "company_header": "某某股份有限公司 · 财务部",
  "findings": [
    {
      "title": "银行未达账",
      "severity": "高",
      "amount": "35万",
      "owner": "出纳",
      "source": "工商银行对账单"
    }
  ],
  "conclusion": "本月不可关账。",
  "open_issues": "工商银行未达 35 万待回单。",
  "data_gaps": "无"
}
```

```bash
cp /workspace/managed/report_templates/<slug>.docx outputs/report-template.docx
python .opencode/skills/docx/scripts/fill_template.py \
  --template outputs/report-template.docx \
  --data outputs/report-data.json \
  --output outputs/report.docx
```

Word can split `{{placeholder}}` across runs. Always use this script. Do not
do simple string replacement.

The JSON file must be an object. Keys can include or omit braces. These are
equivalent: `client_name` and `{{client_name}}`.

## Reading Document Text

For ordinary text, load with `python-docx` and read paragraphs and tables.

```python
from docx import Document

doc = Document("input.docx")
texts = [p.text for p in doc.paragraphs if p.text]
for table in doc.tables:
    for row in table.rows:
        texts.append("\t".join(cell.text for cell in row.cells))
```

`python-docx` does not expose every review feature. For comments and tracked changes, inspect the OOXML files inside the `.docx` package.

## Comments and Tracked Changes

Use the extraction script when the user asks about comments, redlines, insertions, or deletions.

```bash
python .opencode/skills/docx/scripts/read_comments.py --input reviewed.docx --output outputs/review.json
```

The script reads `word/comments.xml` for comments and scans `word/document.xml` for `w:ins` and `w:del` tracked changes. If those files are absent, report that the document has no extractable comments or tracked changes.

## Converting to PDF

When the user asks for a PDF version of a Word document, use LibreOffice headless conversion.

```bash
mkdir -p outputs
soffice --headless --convert-to pdf --outdir outputs document.docx
```

Check that the PDF file exists before reporting success.

## Dependencies

- `pip install python-docx` - create and edit Word documents
- LibreOffice (`soffice`) - convert DOCX to PDF
