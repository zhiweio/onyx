---
name: litigation-analysis-qcc
description: Analyze litigation and judgments for a named company from Qichacha. Use for 诉讼, 案件, or 裁判文书.
required-mcp:
  - qcc-legal-case
  - qcc-risk
---

# litigation-analysis-qcc

List cases with 案号, court, and status. Do not invent a 案号.

Official guide: https://agent.qcc.com/skill/v1/litigation-analysis-qcc/SKILL.md
Save raw MCP bodies under `outputs/mcp/qichacha/`. Never invent a 案号 or 统一社会信用代码.
