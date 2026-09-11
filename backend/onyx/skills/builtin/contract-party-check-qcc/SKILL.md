---
name: contract-party-check-qcc
description: Check contract parties on Qichacha. Use for 合同相对方, 签约主体.
required-mcp:
  - qcc-company
  - qcc-legal-case
  - qcc-risk
---

# contract-party-check-qcc

Match the signed name to the registry.

Official guide: https://agent.qcc.com/skill/v1/contract-party-check-qcc/SKILL.md
Save raw MCP bodies under `outputs/mcp/qichacha/`. Never invent a 案号 or 统一社会信用代码.
