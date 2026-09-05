---
name: tax-policy-trend
description: Research China tax policy trends and write a cited outlook. Use for 政策, 趋势, 公告, 税率变化, or industry tax planning.
---

# tax-policy-trend

Produce a cited China tax policy trend note.

## Workflow

1. Clarify tax type (VAT, CIT, IIT, customs) and region / industry if given.
2. Call `tax_live_query` with intent `policy` against `sta_policy` and `tax_reference`.
3. Call `tax_live_query` with intent `news` against `tax_intel`.
4. If patents or R&D incentives matter, query `patsnap_mcp` when configured.
5. Write:
   - What changed
   - Who is affected
   - Effective dates
   - Open implementation questions
   - Sources

## Rules

- Quote document numbers and issuing bodies from the fetched records.
- Separate official policy from news commentary.
- Do not treat a news snippet as an enacted rule.
