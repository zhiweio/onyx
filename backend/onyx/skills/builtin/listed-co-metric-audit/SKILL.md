---
name: listed-co-metric-audit
description: Audit listed-company metrics from normalized statements. Prove ties, compute ratios, and flag restatements. Use for 勾稽, 比率, or metric audit.
---

# listed-co-metric-audit

Scripts only. Do not call MCP.

Inputs: `outputs/normalized/*.csv` from `listed-co-filings-normalize`.

1. Prove 三表勾稽. Write breaks to `outputs/exceptions/statement_ties.csv`.
2. Compute ratios with formula and 取数科目. Write `outputs/normalized/ratios.csv`.
3. Compare 同比 / 环比 only against named base periods.

Refuse to fill a missing line. A broken tie stays in the exception file.
