---
name: license-validation-qcc
description: Validate licenses and permits from Qichacha MCP. Use for 资质核验 or 行政许可.
required-mcp:
  - qcc-company
optional-mcp:
  - qcc-operation
  - qcc-legal-regulation
---

# license-validation-qcc

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

Official skill: https://agent.qcc.com/skill/v1/legal/license-validation-qcc/SKILL.md

## Task

Check named licenses against current filings.

## Phases

1. **anchor** — `get_company_registration_info`.
2. **permits** — `get_administrative_license` on `qcc-company`. If
   `qcc-operation` is up, `get_qualifications` and `get_telecom_license`.
3. **rules** — If `qcc-legal-regulation` is up, search the named rule.
4. **write** — License memo. Mark expired items from the tool dates.
