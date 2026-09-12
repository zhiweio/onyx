---
name: executive-background-qcc
description: Screen executives from Qichacha MCP person tools. Use for 高管背景 or 董监高.
required-mcp:
  - qcc-executive
optional-mcp:
  - qcc-company
---

# executive-background-qcc

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

Official skill: https://agent.qcc.com/skill/v1/banking/executive-background-qcc/SKILL.md

## Task

Default: all 董监高 plus 实际控制人. Quick mode: 法定代表人, 实际控制人,
董事长, 总经理. Single-person mode: one name.

## Phases

1. **roster** — `get_key_personnel` on `qcc-company` when that server
   is up.
2. **scan** — For each target, `get_executive_risk_scan` with company
   key plus person name.
3. **drill** — Hits among `get_executive_dishonest`,
   `get_executive_high_consumption_ban`, `get_executive_exit_restriction`,
   `get_executive_judgment_debtor`.
4. **write** — Person memo. Do not loop every atom tool first.
