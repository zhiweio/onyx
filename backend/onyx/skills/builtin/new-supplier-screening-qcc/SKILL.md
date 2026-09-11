---
name: new-supplier-screening-qcc
description: Screen a new supplier on Qichacha. Use for 新供方, 准入筛查.
required-mcp:
  - qcc-company
  - qcc-risk
---

# new-supplier-screening-qcc

Refuse to clear a supplier with unresolved identity.

Official guide: https://agent.qcc.com/skill/v1/new-supplier-screening-qcc/SKILL.md
Save raw MCP bodies under `outputs/mcp/qichacha/`. Never invent a 案号 or 统一社会信用代码.
