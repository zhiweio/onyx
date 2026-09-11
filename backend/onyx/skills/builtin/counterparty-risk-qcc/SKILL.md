---
name: counterparty-risk-qcc
description: Score a counterparty's Qichacha risk signals. Use for 交易对手, 合作方风险.
required-mcp:
  - qcc-risk
  - qcc-company
---

# counterparty-risk-qcc

Name each risk signal and its source tool.

Official guide: https://agent.qcc.com/skill/v1/counterparty-risk-qcc/SKILL.md
Save raw MCP bodies under `outputs/mcp/qichacha/`. Never invent a 案号 or 统一社会信用代码.
