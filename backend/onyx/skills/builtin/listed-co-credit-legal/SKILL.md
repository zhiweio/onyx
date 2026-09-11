---
name: listed-co-credit-legal
description: Collect credit, legal, executive, and operating-risk facts for a listed company from Qichacha. Use for 诉讼, 失信, 股权, or credit legal review.
optional-mcp:
  - qcc-risk
  - qcc-legal-case
  - qcc-legal-regulation
  - qcc-executive
  - qcc-operation
---

# listed-co-credit-legal

Read `outputs/entity.json`. Call only the Qichacha servers that are installed
and authenticated.

Write `outputs/credit/legal.md` and raw bodies under `outputs/mcp/qichacha/`.
Every 案号, penalty, and shareholder change must come from a tool. Prefer
domain skills (`litigation-analysis-qcc`, `credit-due-diligence-qcc`) when
the question is narrow.
