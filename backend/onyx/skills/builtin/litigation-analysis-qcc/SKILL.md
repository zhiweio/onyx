---
name: litigation-analysis-qcc
description: Map current and historical litigation from Qichacha MCP. Use for 诉讼, 立案, or case risk.
required-mcp:
  - qcc-risk
optional-mcp:
  - qcc-history
  - qcc-executive
  - qcc-company
---

# litigation-analysis-qcc

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

Official skill: https://agent.qcc.com/skill/v1/banking/litigation-analysis-qcc/SKILL.md

## Task

Cover current cases, history, and key people. Rate residual case risk.

## Phases

1. **anchor** — Lock the entity on `qcc-company` when that server is up.
2. **scan** — `get_company_risk_scan` on `qcc-risk`.
3. **current** — Drill hits among `get_judicial_documents`,
   `get_case_filing_info`, `get_hearing_notice`, `get_court_notice`,
   `get_judgment_debtor_info`, `get_dishonest_info`,
   `get_high_consumption_restriction`, `get_terminated_cases`,
   `get_default_info`.
4. **history** — If `qcc-history` is up, call the matching
   `get_historical_*` tools for the same hits.
5. **people** — For 法定代表人 and 实际控制人, call
   `get_executive_risk_scan` then drill.
6. **write** — Case memo. Quote 案号 from the tool only.
