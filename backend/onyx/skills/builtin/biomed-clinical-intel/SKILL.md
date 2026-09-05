---
name: biomed-clinical-intel
description: Map clinical pipelines and competing trials for an indication or asset. Use for 临床, 管线, ClinicalTrials, Chinadrugtrials, or competitive trials.
---

# biomed-clinical-intel

Produce a cited clinical pipeline scan. Prefer live registries over memory.

## Workflow

1. Identify the indication, asset class, phase, and geography if given.
2. Search ClinicalTrials.gov, Chinadrugtrials, and CDE trial disclosures with the browser or web search.
3. Record NCT or China registry IDs, sponsor, phase, status, and primary endpoint when present.
4. Write:
   - Active and recent trials that compete or inform the program
   - Design patterns and endpoints
   - Open questions
   - Sources

## Rules

- Cite every trial with a registry ID or official URL.
- Do not invent NCT numbers, enrollment, or readout dates.
- Registry pages outrank news.
- If a registry cannot be fetched, say it is unavailable.
