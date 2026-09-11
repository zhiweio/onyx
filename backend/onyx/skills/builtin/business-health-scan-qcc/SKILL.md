---
name: business-health-scan-qcc
description: Scan operating health from Qichacha company, operation, and risk data. Use for 经营健康, 体检.
required-mcp:
  - qcc-company
  - qcc-operation
  - qcc-risk
---

# business-health-scan-qcc

Summarize status, operations, and open risks.

Official guide: https://agent.qcc.com/skill/v1/business-health-scan-qcc/SKILL.md
Save raw MCP bodies under `outputs/mcp/qichacha/`. Never invent a 案号 or 统一社会信用代码.
