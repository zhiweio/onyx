---
name: guarantor-check-qcc
description: Check a guarantor from Qichacha MCP credit and case data. Use for 担保人 or 保证人.
required-mcp:
  - qcc-company
  - qcc-risk
optional-mcp:
  - qcc-executive
---

# guarantor-check-qcc

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

Official skill: https://agent.qcc.com/skill/v1/banking/guarantor-check-qcc/SKILL.md

## Task

Cover identity, asset stress, and personal fallback.

## Phases

1. **anchor** — `get_company_registration_info` and `get_financial_data`.
2. **scan** — `get_company_risk_scan`. Drill `get_equity_freeze`,
   `get_guarantee_info`, `get_dishonest_info`.
3. **people** — If `qcc-executive` is up, `get_executive_risk_scan` for
   法定代表人 and 实际控制人.
4. **write** — Guarantor memo.
