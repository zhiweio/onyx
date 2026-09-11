---
name: credit-monitoring-qcc
description: Monitor Qichacha risk changes for a named company. Use for 贷后, 风险监测.
required-mcp:
  - qcc-risk
---

# credit-monitoring-qcc

Compare current risk to the last extract if one exists.

Official guide: https://agent.qcc.com/skill/v1/credit-monitoring-qcc/SKILL.md
Save raw MCP bodies under `outputs/mcp/qichacha/`. Never invent a 案号 or 统一社会信用代码.
