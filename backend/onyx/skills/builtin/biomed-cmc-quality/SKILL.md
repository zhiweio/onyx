---
name: biomed-cmc-quality
description: Assess CMC and quality risk from public labels, guidances, and recall notices. Use for CMC, 质量, 药学, inspection, or recall risk.
---

# biomed-cmc-quality

Produce a cited CMC and quality risk brief. Prefer live official sources over memory.

## Workflow

1. Identify the product, dosage form, and manufacturing region if given.
2. Search FDA, EMA, NMPA, and CDE CMC guidances, labels, and recall or inspection notices.
3. Extract process, control, impurity, or stability issues that apply.
4. Write:
   - Findings with source URL
   - Risk level (high / medium / low) and why
   - Open CMC questions
   - Recommended next checks

## Rules

- Cite every material claim with URL and issuing body.
- Official guidances and labels outrank news.
- Do not invent inspection outcomes, batch numbers, or impurity limits.
- If a source cannot be fetched, say it is unavailable.
