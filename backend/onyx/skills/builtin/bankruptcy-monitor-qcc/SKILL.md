---
name: bankruptcy-monitor-qcc
description: Monitor bankruptcy and reorganization signals on Qichacha. Use for 破产, 重整.
required-mcp:
  - qcc-risk
  - qcc-legal-case
---

# bankruptcy-monitor-qcc

Cite the case or announcement. Do not infer bankruptcy from rumor.

Official guide: https://agent.qcc.com/skill/v1/bankruptcy-monitor-qcc/SKILL.md
Save raw MCP bodies under `outputs/mcp/qichacha/`. Never invent a 案号 or 统一社会信用代码.
