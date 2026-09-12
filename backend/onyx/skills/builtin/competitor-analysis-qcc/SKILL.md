---
name: competitor-analysis-qcc
description: Compare peers from Qichacha MCP operating data. Use for 竞品 or competitor scan.
required-mcp:
  - qcc-company
  - qcc-operation
optional-mcp:
  - qcc-ipr
---

# competitor-analysis-qcc

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

Official skill: https://agent.qcc.com/skill/v1/invest/competitor-analysis-qcc/SKILL.md

## Task

Compare two or more named peers. Stop if a peer name is ambiguous.

## Phases

1. **anchor** — Lock each peer on `qcc-company`.
2. **ops** — `get_bidding_info`, `get_financing_records`,
   `get_recruitment_info`.
3. **ip** — If `qcc-ipr` is up, `get_patent_info` per peer.
4. **write** — Peer table. Do not invent a peer the user did not name.
