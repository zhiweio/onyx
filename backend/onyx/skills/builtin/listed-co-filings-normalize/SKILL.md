---
name: listed-co-filings-normalize
description: Normalize listed-company filings into comparable period tables. Use for 年报, 半年报, 财务附注, or filing ingest.
optional-mcp:
  - hithink-a-share
---

# listed-co-filings-normalize

Prefer HiThink A-share filings when authenticated. Otherwise run
`document-ingest` on uploaded PDFs / workbooks.

Write:

- `outputs/normalized/income.csv`
- `outputs/normalized/balance.csv`
- `outputs/normalized/cashflow.csv`
- `outputs/normalized/periods.md` (币种, unit, 准则, source file)

Do not invent a missing line. Mark gaps in `outputs/normalized/gaps.md`.
Use `xlsx` and recalculate workbooks that may have stale formulas.
