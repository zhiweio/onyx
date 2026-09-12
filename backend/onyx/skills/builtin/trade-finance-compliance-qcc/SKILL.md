---
name: trade-finance-compliance-qcc
description: Check trade-finance compliance from Qichacha MCP customs and tax data. Use for 贸易融资 or 进出口合规.
required-mcp:
  - qcc-company
  - qcc-operation
optional-mcp:
  - qcc-risk
---

# trade-finance-compliance-qcc

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

Official skill: https://agent.qcc.com/skill/v1/banking/trade-finance-compliance-qcc/SKILL.md

## Task

Cover customs credit, tax status, and trade risk.

## Phases

1. **anchor** — `get_company_registration_info`.
2. **trade** — `get_import_export_credit` and `get_taxpayer_qualification`.
3. **ops** — `get_credit_evaluation` and `get_qualifications` on
   `qcc-operation`.
4. **scan** — If `qcc-risk` is up, `get_company_risk_scan` then
   `get_tax_arrears_notice` / `get_tax_violation` / `get_entry_denied`
   on hits.
5. **write** — Trade-finance memo.
