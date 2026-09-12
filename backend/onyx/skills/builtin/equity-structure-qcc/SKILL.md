---
name: equity-structure-qcc
description: Map equity and control from Qichacha MCP. Use for 股权穿透 or 实控人.
required-mcp:
  - qcc-executive
  - qcc-company
---

# equity-structure-qcc

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

Official skill: https://agent.qcc.com/skill/v1/banking/equity-structure-qcc/SKILL.md

## Task

Map shareholders, controller, and UBO.

## Phases

1. **anchor** — `get_company_registration_info`.
2. **owners** — `get_shareholder_info`, `get_actual_controller`,
   `get_beneficial_owners`. Quote 总持股 and 表决权 as returned.
3. **graph** — `get_executive_controlled_companies` and
   `get_executive_related_companies` for the controller.
4. **write** — Equity memo. Do not invent a holding platform.
