---
name: tax-compliance
description: Assess China tax compliance risk for a company using live policy, enforcement, and commercial MCP sources. Use for 合规, 稽查, 违法, 风险预警, VAT/CIT exposure, or credit checks.
---

# tax-compliance

Produce a cited China tax compliance risk brief. Prefer live sources over memory.

## Workflow

1. Identify the company name and unified social credit code (统一社会信用代码).
2. Call `tax_live_query` with intent `enforcement` and `company` / `uscc` set.
3. Call `tax_live_query` again for related policy (`sta_policy`, `tax_reference`).
4. If 启信宝 MCP is configured, include credit and judicial hits. If it is not configured, say so.
5. Write a risk brief with:
   - Findings (each with source URL and trust tier)
   - Risk level (high / medium / low) and why
   - Open questions
   - Recommended next checks

## Rules

- Cite every material claim with URL, source_id, and published date when present.
- Official STA pages outrank news. Commercial MCP results are supporting only.
- Do not invent case numbers, penalties, or policy documents.
- If a plugin returns empty, report that source as unavailable.
