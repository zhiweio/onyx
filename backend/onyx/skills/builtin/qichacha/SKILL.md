---
name: qichacha
description: Route Qichacha / 企查查 company, risk, legal, IP, and tender lookups. Use for 企查查, 工商, 股权, 诉讼, or 招投标.
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

Pick the Qichacha server that matches the question. Do not enable all ten
servers for a name lookup.

| Need | Server |
| --- | --- |
| 工商 / 基本信息 | qcc-company |
| 风险 / 失信 | qcc-risk |
| 知识产权 | qcc-ipr |
| 经营 / 招投标线索 | qcc-operation, qcc-tender |
| 高管 / 股权 | qcc-executive |
| 诉讼 | qcc-legal-case |
| 行政处罚 | qcc-legal-regulation |
| 历史沿革 | qcc-history (needs enterprise cert) |
| 附件 | qcc-document |

Prefer a domain skill (`credit-due-diligence-qcc`, `litigation-analysis-qcc`,
…) when the task matches. Save raw bodies under `outputs/mcp/qichacha/`.
Never invent a 案号 or 统一社会信用代码.
