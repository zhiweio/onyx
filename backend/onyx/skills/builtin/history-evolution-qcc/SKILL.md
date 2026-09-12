---
name: history-evolution-qcc
description: Trace company history from Qichacha MCP history tools. Needs the history server certificate. Use for 历史沿革.
required-mcp:
  - qcc-history
  - qcc-company
optional-mcp:
  - qcc-executive
  - qcc-ipr
---

# history-evolution-qcc

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

Official skill: https://agent.qcc.com/skill/v1/invest/history-evolution-qcc/SKILL.md

## Task

Build a timeline of names, capital, legal reps, and owners.

## Phases

1. **now** — `get_company_registration_info` and `get_change_records`.
2. **history** — `get_historical_registration`, `get_historical_legal_rep`,
   `get_historical_shareholders`, `get_historical_executives`.
3. **gap** — If `qcc-history` is down, say so and stop at current
   registry. Do not invent past names.
4. **write** — History memo.
