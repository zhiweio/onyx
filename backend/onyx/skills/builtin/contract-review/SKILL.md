---
name: contract-review
description: Review a contract for party, term, and compliance issues using Qichacha MCP. Use for 合同审查.
required-mcp:
  - qcc-company
  - qcc-risk
optional-mcp:
  - qcc-operation
---

# contract-review

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

Official skill: https://agent.qcc.com/skill/v1/legal/contract-review/SKILL.md

## Task

Review the uploaded contract. Do not edit the source text. Verify each
Chinese party on official MCP, then review clauses.

## Phases

1. **read** — Extract each party name, credit code, and 法定代表人 from
   the contract.
2. **anchor** — For each Chinese company, `get_company_by_query` if
   needed, then `verify_company_accuracy` and
   `get_company_registration_info`.
3. **scan** — `get_company_risk_scan` per party. Drill hits.
4. **ops** — If `qcc-operation` is up and the contract needs a license,
   `get_qualifications`.
5. **clauses** — Review form, commercial, and legal terms against the
   contract text only.
6. **write** — Review memo plus comments. Mark data source as 企查查 MCP.
   Do not fall back to web search for registry facts.
