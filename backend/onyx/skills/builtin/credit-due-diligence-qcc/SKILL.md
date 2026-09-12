---
name: credit-due-diligence-qcc
description: Run credit due diligence from Qichacha MCP company, risk, and history data. Use for 尽调, 授信, or credit DD.
required-mcp:
  - qcc-company
  - qcc-risk
optional-mcp:
  - qcc-history
  - qcc-executive
---

# credit-due-diligence-qcc

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

Official skill: https://agent.qcc.com/skill/v1/banking/credit-due-diligence-qcc/SKILL.md

## Task

Cover registry, finance, risk, repair history, and controller risk.

## Phases

1. **anchor** — `verify_company_accuracy` and
   `get_company_registration_info`.
2. **owners** — `get_shareholder_info` and `get_actual_controller`. Quote
   表决权 as the tool returned it.
3. **finance** — `get_financial_data` and `get_annual_reports`. If finance
   is empty, say so and drop the grade one step.
4. **scan** — `get_company_risk_scan`, then drill hits including
   `get_default_info`, `get_equity_freeze`, and `get_equity_pledge_info`.
5. **history** — If `qcc-history` is up, call historical risk tools and
   name the repair pattern.
6. **people** — `get_executive_risk_scan` for 法定代表人 and 实际控制人.
7. **write** — Credit memo. Rank residual risk. Do not set the limit
   yourself from guessed ratios.
