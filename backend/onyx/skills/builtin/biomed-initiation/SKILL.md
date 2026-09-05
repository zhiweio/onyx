---
name: biomed-initiation
description: Plan and write a cited drug-program initiation report. Use for 立项, target brief, or a multi-source R&D go/no-go memo.
---

# biomed-initiation

Produce a cited initiation report. Follow `long-job-protocol`.

## Phases

1. **plan** — indication, asset, geography, outline in `outputs/plan/PLAN.md`
2. **research** — run `biomed-literature`, `biomed-clinical-intel`, `biomed-patent-fto`, `biomed-cmc-quality` into `outputs/research/<role>/`
3. **compose** — write `outputs/markdown/initiation-report.md` from the notes
4. **review** — check citations, invented IDs, and open questions

## Rules

- Cite PMID, NCT, patent numbers, and agency URLs from fetched records only.
- Query Patsnap MCP when configured; write the raw body under `outputs/mcp/`.
- Do not invent trial IDs or patent numbers.
- Use the `initiation_report` template when `SCENARIO.md` names it.
