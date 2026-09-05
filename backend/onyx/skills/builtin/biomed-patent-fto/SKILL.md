---
name: biomed-patent-fto
description: Draft a freedom-to-operate and patent landscape brief for a molecule, target, or formulation. Use for 专利, FTO, freedom to operate, or IP landscape.
---

# biomed-patent-fto

Produce a cited patent and FTO note. Prefer live patent data over memory.

## Workflow

1. Identify the asset, target, claim type (composition, method, formulation), and jurisdictions.
2. If a Patsnap MCP server is configured, query it for families and legal status.
3. If Patsnap is not configured, search public patent offices and say the commercial feed is missing.
4. Write:
   - Families and assignees that matter
   - Claim themes that may block or enable a program
   - Open FTO questions
   - Sources

## Rules

- Cite patent numbers, assignees, and status from fetched records.
- Do not invent patent numbers, priority dates, or expiry dates.
- Commercial MCP results support the brief. They do not replace official registers.
- If a plugin returns empty, report that source as unavailable.
