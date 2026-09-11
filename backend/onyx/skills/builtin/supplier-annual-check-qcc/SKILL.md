---
name: supplier-annual-check-qcc
description: Run an annual supplier check on Qichacha. Use for 供应商年检.
required-mcp:
  - qcc-company
  - qcc-risk
  - qcc-legal-case
---

# supplier-annual-check-qcc

Compare to last year's extract when present.

Official guide: https://agent.qcc.com/skill/v1/supplier-annual-check-qcc/SKILL.md
Save raw MCP bodies under `outputs/mcp/qichacha/`. Never invent a 案号 or 统一社会信用代码.
