---
name: contract-party-check-qcc
description: Verify a contract counterparty from Qichacha MCP. Use for 合同相对方 or party check.
required-mcp:
  - qcc-company
  - qcc-risk
optional-mcp:
  - qcc-history
  - qcc-executive
  - qcc-operation
---

# contract-party-check-qcc

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

Official skill: https://agent.qcc.com/skill/v1/legal/contract-party-check-qcc/SKILL.md

## Task

Rate the party A to D. D means refuse to sign.

## Phases

1. **anchor** — `verify_company_accuracy` and
   `get_company_registration_info`. 吊销 / 注销 / 异常 is D.
2. **history** — If `qcc-history` is up, `get_historical_registration`
   and `get_historical_legal_rep`.
3. **scan** — `get_company_risk_scan`. Drill 失信 / 限高 / 被执行 /
   股权冻结 / 经营异常.
4. **people** — `get_executive_risk_scan` for 法定代表人.
5. **ops** — If `qcc-operation` is up, `get_bidding_info` and
   `get_recruitment_info`.
6. **write** — Party-check memo. Do not call `get_company_profile`.
