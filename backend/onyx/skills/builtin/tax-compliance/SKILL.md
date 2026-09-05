---
name: tax-compliance
description: Assess China tax compliance risk for a company using configured commercial MCP sources. Use for 合规, 稽查, 违法, 风险预警, VAT/CIT exposure, or credit checks.
---

# tax-compliance

Produce a cited China tax compliance risk brief. Prefer live MCP sources over memory.

## Workflow

1. Identify the company name and unified social credit code (统一社会信用代码).
2. If a Qixinbao or Tianyancha MCP server is configured, query credit, enforcement, and judicial records.
3. If those MCP servers are not configured, say so and do not invent filings or cases.
4. Write a risk brief with:
   - Findings (each with source URL when present)
   - Risk level (high / medium / low) and why
   - Open questions
   - Recommended next checks

## Rules

- Cite every material claim with URL and published date when present.
- Commercial MCP results are supporting only. Do not treat them as official STA filings.
- Do not invent case numbers, penalties, or policy documents.
- If a tool returns empty, report that source as unavailable.
