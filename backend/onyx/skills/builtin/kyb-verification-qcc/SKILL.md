---
name: kyb-verification-qcc
description: Verify a company's registration, status, and identity from Qichacha MCP. Use for KYB, 工商核验, or 主体核验.
required-mcp:
  - qcc-company
  - qcc-risk
optional-mcp:
  - qcc-history
  - qcc-executive
  - qcc-operation
---

# kyb-verification-qcc

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

Official skill: https://agent.qcc.com/skill/v1/banking/kyb-verification-qcc/SKILL.md

## Task

Verify registration, status, and credit code. Rate A to D.

## Phases

1. **anchor** — `get_company_by_query`, then `verify_company_accuracy` and
   `get_company_registration_info` on `qcc-company`. Stop if the name or
   credit code does not match, or if 登记状态 is 吊销 / 注销 / 异常.
2. **owners** — `get_shareholder_info`, `get_actual_controller`,
   `get_beneficial_owners`. Drill a new holding platform with
   `get_shareholder_info` before you call a control change.
3. **history** — If `qcc-history` is up, call `get_historical_registration`,
   `get_historical_legal_rep`, and `get_historical_shareholders`.
4. **scan** — `get_company_risk_scan`, then drill hits. Always drill
   `get_default_info`.
5. **people** — For each UBO, call `get_executive_risk_scan` on
   `qcc-executive`. Drill only count > 0.
6. **write** — KYB memo. Do not decide the account for the user.
