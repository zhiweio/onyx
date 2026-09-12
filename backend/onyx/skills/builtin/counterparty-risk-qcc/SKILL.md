---
name: counterparty-risk-qcc
description: Score a trade counterparty from Qichacha MCP risk and customs data. Use for 交易对手 or counterparty risk.
required-mcp:
  - qcc-risk
  - qcc-company
optional-mcp:
  - qcc-operation
---

# counterparty-risk-qcc

## Access

Call official Qichacha MCP tools through the Onyx gateway. Official MCP
already dehydrates long lists. The gateway caches the full body. See
https://agent.qcc.com/guide.

Do not run `qcc`, `qcc-agent-cli`, `npx qcc-document-mcp`, or any other
Qichacha CLI. Do not ask the user for an API key.

If the name is not a full 登记名 or 18-digit 统一社会信用代码, call
`get_company_by_query` on `qcc-company` and stop when the match is
ambiguous. Lock the credit code before any risk tool.

For two or more risk dimensions, call `get_company_risk_scan` on
`qcc-risk` first. Drill only dimensions with count > 0. Leave `year`
empty for a full set.

Cite only values the tool returned. Never invent a 案号 or 统一社会信用代码.
Save raw bodies under `outputs/mcp/qichacha/`.

Official skill: https://agent.qcc.com/skill/v1/banking/counterparty-risk-qcc/SKILL.md

## Task

Cover identity, trade credit, penalties, and residual risk.

## Phases

1. **anchor** — `get_company_registration_info` on `qcc-company`.
2. **trade** — `get_import_export_credit` and, if `qcc-operation` is up,
   `get_credit_evaluation`.
3. **scan** — `get_company_risk_scan`, then drill
   `get_administrative_penalty`, `get_dishonest_info`, and
   `get_default_info` when they hit.
4. **write** — Counterparty memo.
