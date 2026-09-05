---
name: xlsx
description: Use this skill when an Excel .xlsx workbook or spreadsheet must be read, analyzed, created, styled, recalculated, charted, or converted; trigger on xlsx, Excel, workbook, spreadsheet, worksheet, formula, chart, table, CSV, or cells.
---

# XLSX Skill

> **Path convention**: All commands run from the **session workspace** (your working directory). Never `cd` into the skill directory. Prefix all skill scripts with `.opencode/skills/xlsx/`. All generated files (workbooks, CSV exports, charts, JSON summaries) go in `outputs/`.

## Quick Reference

| Task | Guide |
|------|-------|
| Inspect a workbook | `python .opencode/skills/xlsx/scripts/inspect_workbook.py --input workbook.xlsx` |
| Recalculate formulas | `python .opencode/skills/xlsx/scripts/recalculate.py --input workbook.xlsx --output outputs/recalculated.xlsx` |
| Preserve formatting | Use `openpyxl` |
| Bulk analysis | Use `pandas` |
| Deep details | Read [reference.md](reference.md) |

---

## Choosing the Tool

Use `openpyxl` when the task involves workbook structure: styles, formulas, charts, merged cells, column widths, freeze panes, named sheets, or existing formatting.

Use `pandas` when the task is tabular analysis: grouping, filtering, joins, pivots, statistics, or conversion to and from CSV. After analysis, write final presentation workbooks with `openpyxl` if formatting matters.

## Reading Workbooks

For large sheets, use read-only streaming mode.

```python
from openpyxl import load_workbook

wb = load_workbook("input.xlsx", read_only=True, data_only=False)
ws = wb.active
for row in ws.iter_rows(values_only=True):
    ...
```

Use the inspection script before editing an unfamiliar file.

```bash
python .opencode/skills/xlsx/scripts/inspect_workbook.py --input workbook.xlsx --max-rows 5
```

## Formula Values

`openpyxl` does not calculate formulas. It can read formulas or cached results, but it cannot make cached results current.

- Use `data_only=False` to read formula text.
- Use `data_only=True` only when the file was last saved by Excel, LibreOffice, or another spreadsheet app that recalculated it.
- If formulas may be stale, recalculate first.

```bash
python .opencode/skills/xlsx/scripts/recalculate.py --input model.xlsx --output outputs/model-recalculated.xlsx
```

## Writing Values and Formats

```python
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

wb = Workbook()
ws = wb.active
ws.title = "Summary"
ws["A1"] = "Revenue"
ws["B1"] = 125000
ws["A1"].font = Font(bold=True)
ws["B1"].number_format = "$#,##0"
ws["A1"].fill = PatternFill("solid", fgColor="D9EAF7")
ws.column_dimensions["A"].width = 24
ws.freeze_panes = "A2"
wb.save("outputs/summary.xlsx")
```

## Conditional Formatting

Use conditional formatting for heatmaps, thresholds, and exception highlighting.

```python
from openpyxl.formatting.rule import ColorScaleRule

ws.conditional_formatting.add(
    "B2:B100",
    ColorScaleRule(
        start_type="min", start_color="F8696B", end_type="max", end_color="63BE7B"
    ),
)
```

## Charts

Use `openpyxl.chart` for native Excel charts. Place charts on the worksheet near the source data and save the workbook.

```python
from openpyxl.chart import BarChart, Reference

chart = BarChart()
chart.title = "Revenue by Region"
data = Reference(ws, min_col=2, min_row=1, max_row=5)
cats = Reference(ws, min_col=1, min_row=2, max_row=5)
chart.add_data(data, titles_from_data=True)
chart.set_categories(cats)
ws.add_chart(chart, "D2")
```

## Dependencies

- `pip install openpyxl` - workbook structure, formulas, styles, and charts
- `pip install pandas` - bulk tabular analysis
- LibreOffice (`soffice`) - headless formula recalculation
