---
name: ip-asset-inventory-qcc
description: Inventory patents, trademarks, and copyrights from Qichacha MCP. Use for 知产清单.
required-mcp:
  - qcc-ipr
optional-mcp:
  - qcc-company
---

# ip-asset-inventory-qcc

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

Official skill: https://agent.qcc.com/skill/v1/invest/ip-asset-inventory-qcc/SKILL.md

## Task

List patents, trademarks, software copyrights, and works.

## Phases

1. **anchor** — Lock the entity when `qcc-company` is up.
2. **ip** — `get_patent_info`, `get_trademark_info`,
   `get_software_copyright_info`, `get_copyright_work_info` on `qcc-ipr`.
3. **page** — Use the official page fields when the tool supports them.
   Do not invent extra pages.
4. **write** — IP inventory.
