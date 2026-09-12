---
name: strip-profile-qcc
description: Build a one-page company profile from Qichacha MCP. Use for 企业画像 or strip profile.
required-mcp:
  - qcc-company
optional-mcp:
  - qcc-executive
  - qcc-risk
  - qcc-ipr
---

# strip-profile-qcc

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

Official skill: https://agent.qcc.com/skill/v1/invest/strip-profile-qcc/SKILL.md

## Task

One page: registry, owners, top risks, IP.

## Phases

1. **anchor** — `get_company_registration_info` and `get_company_profile`.
2. **owners** — `get_shareholder_info` and `get_actual_controller`.
3. **scan** — If `qcc-risk` is up, `get_company_risk_scan`.
4. **ip** — If `qcc-ipr` is up, `get_patent_info` and `get_trademark_info`.
5. **write** — One-page profile.
