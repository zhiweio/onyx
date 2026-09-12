---
name: ubo-screening-qcc
description: Find beneficial owners from Qichacha MCP equity tools. Use for UBO, 受益所有人, or 反洗钱.
required-mcp:
  - qcc-executive
  - qcc-company
optional-mcp:
  - qcc-risk
---

# ubo-screening-qcc

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

Official skill: https://agent.qcc.com/skill/v1/banking/ubo-screening-qcc/SKILL.md

## Task

Trace owners to natural persons at the 25% line.

## Phases

1. **anchor** — Lock the entity on `qcc-company`.
2. **owners** — `get_shareholder_info`, `get_actual_controller`,
   `get_beneficial_owners`. Quote 受益股份 as returned.
3. **confirm** — `get_executive_beneficial_owner` on `qcc-executive` for
   each natural person.
4. **people** — `get_executive_risk_scan` per UBO, then drill hits.
5. **write** — UBO file. Do not multiply share layers.
