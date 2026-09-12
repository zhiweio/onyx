---
name: listed-co-credit-legal
description: Collect credit, legal, executive, and operating-risk facts for a listed company from Qichacha MCP. Use for 诉讼, 失信, 股权, or credit legal review.
optional-mcp:
  - qcc-risk
  - qcc-company
  - qcc-executive
  - qcc-operation
  - qcc-history
---

# listed-co-credit-legal

Call official Qichacha MCP tools through the Onyx gateway. Official MCP
already dehydrates long lists. The gateway caches the full body.

Do not run `qcc`, `qcc-agent-cli`, or any other Qichacha CLI.

Read `outputs/entity.json`. Call only the Qichacha servers that are
installed and authenticated.

1. **scan** — `get_company_risk_scan` on `qcc-risk`.
2. **drill** — Hits among litigation, execution, and penalty tools on
   `qcc-risk`.
3. **people** — If `qcc-executive` is up, `get_executive_risk_scan` for
   法定代表人 and 实际控制人.
4. **ops** — If `qcc-operation` is up, `get_company_announcement` or
   `get_related_announcement`.

Write `outputs/credit/legal.md` and raw bodies under
`outputs/mcp/qichacha/`. Every 案号, penalty, and shareholder change
must come from a tool. Prefer domain skills
(`litigation-analysis-qcc`, `credit-due-diligence-qcc`) when the
question is narrow.
