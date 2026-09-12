---
name: labor-compliance-qcc
description: Screen labor and payroll compliance from Qichacha MCP. Use for 劳动合规 or 劳动仲裁.
required-mcp:
  - qcc-risk
optional-mcp:
  - qcc-company
  - qcc-legal-regulation
---

# labor-compliance-qcc

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

Official skill: https://agent.qcc.com/skill/v1/legal/labor-compliance-qcc/SKILL.md

## Task

Cover labor notices, tax arrears, and related cases.

## Phases

1. **anchor** — Lock the entity when `qcc-company` is up.
2. **scan** — `get_company_risk_scan`.
3. **drill** — `get_service_announcement`, `get_tax_arrears_notice`,
   `get_administrative_penalty` on hits.
4. **rules** — If `qcc-legal-regulation` is up and the user named a
   statute, `get_legal_regulation_search`.
5. **write** — Labor memo.
