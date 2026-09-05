# XLSX Reference

An `.xlsx` file is a ZIP package of XML parts. `openpyxl` hides most XML details, but the package model explains many edge cases.

## Cached Formula Values

Spreadsheet files store formulas and may also store cached formula results. `openpyxl` can read either view:

- `data_only=False` returns formulas such as `=SUM(B2:B10)`.
- `data_only=True` returns cached results when the workbook has them.

The cached result can be missing or stale. `openpyxl` does not recalculate it. Save the workbook with a spreadsheet engine such as LibreOffice before reading computed values.

## Cell Coordinates

Excel coordinates are one-based. `A1` is row 1, column 1. Use helpers instead of hand-written math.

```python
from openpyxl.utils import get_column_letter, column_index_from_string

letter = get_column_letter(28)  # AB
index = column_index_from_string("AB")  # 28
```

## Number Formats

Number formats change display, not stored values. Examples:

- `#,##0` for integers with thousands separators.
- `#,##0.00` for two decimals.
- `$#,##0.00` for currency.
- `0.0%` for percentages.
- `yyyy-mm-dd` for dates.

Keep numeric values numeric. Do not preformat numbers as strings unless the value is an identifier.

## Style Objects

Common style classes are `Font`, `PatternFill`, `Border`, `Side`, and `Alignment`. Style objects are immutable in practice: assign a new object or copy an existing one before changing it.

Reuse styles where possible. Creating unique style objects for every cell can make large workbooks slow and oversized.

## Performance Guidance

- Use `read_only=True` for large input workbooks.
- Use `write_only=True` when generating a very large workbook from rows.
- Use `iter_rows(values_only=True)` when formatting is not needed.
- Avoid scanning entire worksheets only to find a small table. Use known bounds when available.
- Save once after a batch of edits, not after each cell.

## When to Use pandas or CSV

Use `pandas` for dataframe operations and export the result to `.xlsx` only at the end. Use CSV when the deliverable is plain data without formulas, styles, merged cells, charts, or multiple sheets.
