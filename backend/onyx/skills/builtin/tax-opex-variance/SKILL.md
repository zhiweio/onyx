---
name: tax-opex-variance
description: Compare department opex across periods. Use for 费用波动, YoY, or MoM expense variance.
---

# tax-opex-variance

Ingest period workbooks, then compute YoY and MoM on `outputs/normalized/opex.csv`.

Explain only large moves that have a source line. Mark unexplained moves in
`outputs/exceptions/opex_unexplained.csv`.
