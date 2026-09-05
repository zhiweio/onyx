---
name: tax-ar-risk
description: Rank high-risk AR customers from aging, collections, and optional credit MCP. Use for 应收高风险 or customer risk lists.
---

# tax-ar-risk

Join aging and collection files. Query a credit MCP (for example Qixin) when
configured. Write raw MCP under `outputs/mcp/`.

Output `outputs/normalized/ar_risk.csv` with aging bucket, days late, and
external flags. Cite the MCP file for each external claim.
