---
name: vendor-assessment-qcc
description: Assess a vendor from Qichacha MCP identity, risk, and operations. Use for 供应商评估 or 准入.
required-mcp:
  - qcc-company
  - qcc-risk
  - qcc-operation
---

# vendor-assessment-qcc

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

Official skill: https://agent.qcc.com/skill/v1/supply/vendor-assessment-qcc/SKILL.md

## Task

Cover identity, 34 risk hits, and operating proof.

## Phases

1. **anchor** — `verify_company_accuracy` and
   `get_company_registration_info`.
2. **scan** — `get_company_risk_scan`, then drill hits.
3. **ops** — `get_qualifications`, `get_credit_evaluation`,
   `get_bidding_info`.
4. **write** — Vendor memo.
