---
name: kyb-verification-qcc
description: Verify a company's registration, status, and identity from Qichacha. Use for KYB, 工商核验, or 主体核验.
required-mcp:
  - qcc-company
---

# kyb-verification-qcc

Verify registration, status, and credit code. Stop if the name is ambiguous.

Official guide: https://agent.qcc.com/skill/v1/kyb-verification-qcc/SKILL.md
Save raw MCP bodies under `outputs/mcp/qichacha/`. Never invent a 案号 or 统一社会信用代码.
