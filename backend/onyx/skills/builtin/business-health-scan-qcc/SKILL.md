---
name: business-health-scan-qcc
description: Scan operating health from Qichacha MCP hiring, bids, and news. Use for 经营健康度.
required-mcp:
  - qcc-company
  - qcc-operation
  - qcc-risk
---

# business-health-scan-qcc

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

Official skill: https://agent.qcc.com/skill/v1/banking/business-health-scan-qcc/SKILL.md

## Task

Separate real operations from a shell.

## Phases

1. **anchor** — `get_company_registration_info` (include 参保人数).
2. **ops** — `get_recruitment_info`, `get_bidding_info`,
   `get_news_sentiment` on `qcc-operation`.
3. **scan** — `get_company_risk_scan` on `qcc-risk`.
4. **write** — Health memo.
