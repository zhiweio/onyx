---
name: credit-monitoring-qcc
description: Watch credit-risk changes from Qichacha MCP. Use for 贷后监控 or credit watch.
required-mcp:
  - qcc-risk
optional-mcp:
  - qcc-company
---

# credit-monitoring-qcc

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

Official skill: https://agent.qcc.com/skill/v1/banking/credit-monitoring-qcc/SKILL.md

## Task

Compare current risk hits to the last known state.

## Phases

1. **anchor** — Lock the entity when `qcc-company` is up.
2. **scan** — `get_company_risk_scan` on `qcc-risk`.
3. **drill** — Hits among `get_dishonest_info`,
   `get_judgment_debtor_info`, `get_high_consumption_restriction`,
   `get_business_exception`, `get_equity_freeze`, `get_default_info`.
4. **write** — Watch memo. Mark new hits vs prior clean dimensions.
