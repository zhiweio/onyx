---
name: tax-expense-rollup
description: Roll subsidiary expense claims into one template. Use for 报销汇总, multi-entity expense, or template-based claim extract.
---

# tax-expense-rollup

Extract claim forms, then pivot by company and department.

## Phases

1. **plan** — name the claim template fields
2. **ingest** — parse docx/xlsx/pdf claims; mark scans `needs_vision`
3. **analyze** — write `outputs/normalized/expenses.csv`
4. **compose** — company × department table plus outliers
5. **review** — confirm totals against MANIFEST file count
