---
name: fundraising-tracker-qcc
description: Trace financing rounds from Qichacha MCP. Use for 融资 or fundraising history.
required-mcp:
  - qcc-company
  - qcc-operation
---

# fundraising-tracker-qcc

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

Official skill: https://agent.qcc.com/skill/v1/invest/fundraising-tracker-qcc/SKILL.md

## Task

List disclosed rounds. Mark missing amounts as 未披露.

## Phases

1. **anchor** — `get_company_registration_info` and `get_listing_info`.
2. **rounds** — `get_financing_records` and `get_investment_institution`.
3. **owners** — `get_shareholder_info` to align later rounds.
4. **write** — Financing table. Do not invent a valuation.
