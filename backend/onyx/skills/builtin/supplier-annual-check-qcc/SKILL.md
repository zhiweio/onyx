---
name: supplier-annual-check-qcc
description: Run an annual supplier check from Qichacha MCP. Use for 供应商年审.
required-mcp:
  - qcc-company
  - qcc-risk
optional-mcp:
  - qcc-operation
---

# supplier-annual-check-qcc

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

Official skill: https://agent.qcc.com/skill/v1/supply/supplier-annual-check-qcc/SKILL.md

## Task

Compare current status, licenses, and risk to last year.

## Phases

1. **anchor** — `get_company_registration_info` and `get_change_records`.
2. **scan** — `get_company_risk_scan`, then drill hits.
3. **ops** — If `qcc-operation` is up, `get_qualifications`.
4. **write** — Annual-check memo.
