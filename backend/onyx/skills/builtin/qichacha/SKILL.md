---
name: qichacha
description: Route Qichacha / 企查查 company, risk, legal, IP, and tender lookups through official MCP. Use for 企查查, 工商, 股权, 诉讼, or 招投标.
optional-mcp:
  - qcc-company
  - qcc-risk
  - qcc-ipr
  - qcc-operation
  - qcc-history
  - qcc-executive
  - qcc-legal-regulation
  - qcc-legal-case
  - qcc-tender
  - qcc-document
---

# qichacha

Read `references/mcp.md` first.

Call official Qichacha MCP tools through the Onyx gateway. Official MCP
already dehydrates long lists. The gateway caches the full body. Guide:
https://agent.qcc.com/guide.

Do not run `qcc`, `qcc-agent-cli`, `npx qcc-document-mcp`, or any other
Qichacha CLI. Do not enable all ten servers for a name lookup.

| Need | Server |
| --- | --- |
| 工商 / 基本信息 | qcc-company |
| 风险 / 失信 / 诉讼记录 | qcc-risk |
| 知识产权 | qcc-ipr |
| 经营 / 招投标线索 | qcc-operation, qcc-tender |
| 高管 / 股权 | qcc-executive |
| 类案检索 | qcc-legal-case |
| 法规检索 | qcc-legal-regulation |
| 历史沿革 | qcc-history (needs enterprise cert) |
| 在线附件解析 | qcc-document |

Prefer a domain skill (`credit-due-diligence-qcc`, `litigation-analysis-qcc`,
…) when the task matches.

If the name is not a full 登记名 or 18-digit 统一社会信用代码, call
`get_company_by_query` on `qcc-company` and stop when the match is
ambiguous.

Save raw bodies under `outputs/mcp/qichacha/`. Never invent a 案号 or
统一社会信用代码.
