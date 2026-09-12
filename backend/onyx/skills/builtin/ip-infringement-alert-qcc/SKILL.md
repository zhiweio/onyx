---
name: ip-infringement-alert-qcc
description: Flag trademark and patent clash risk from Qichacha MCP. Use for 知产侵权预警.
required-mcp:
  - qcc-ipr
optional-mcp:
  - qcc-risk
  - qcc-legal-case
---

# ip-infringement-alert-qcc

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

Official skill: https://agent.qcc.com/skill/v1/legal/ip-infringement-alert-qcc/SKILL.md

## Task

Compare the named mark or product to registered IP.

## Phases

1. **ip** — `get_trademark_info` and `get_patent_info` on `qcc-ipr`.
2. **cases** — If `qcc-risk` is up, `get_company_risk_scan` then
   `get_judicial_documents` for IP hits.
3. **similar** — If `qcc-legal-case` is up and the user wants similar
   cases, `get_judicial_case_search`.
4. **write** — Alert memo. Do not decide infringement as a court.
