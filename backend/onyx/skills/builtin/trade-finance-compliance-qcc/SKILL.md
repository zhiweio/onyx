---
name: trade-finance-compliance-qcc
description: Check trade-finance counterparties on Qichacha. Use for 贸易融资, 保理, 合规.
required-mcp:
  - qcc-company
  - qcc-operation
---

# trade-finance-compliance-qcc

Check registration, operations, and sanctions-like lists available on the server.

Official guide: https://agent.qcc.com/skill/v1/trade-finance-compliance-qcc/SKILL.md
Save raw MCP bodies under `outputs/mcp/qichacha/`. Never invent a 案号 or 统一社会信用代码.
