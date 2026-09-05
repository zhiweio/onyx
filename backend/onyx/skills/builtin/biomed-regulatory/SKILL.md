---
name: biomed-regulatory
description: Map the drug/biologic regulatory pathway across NMPA, FDA, and EMA and the evidence each filing needs, including expedited routes and agency-interaction milestones. Use for 注册申报, 药监, 注册策略, 沟通交流, IND, NDA, BLA, ANDA, 505(b)(2), MAA, CTA, or regulatory strategy.
---

# biomed-regulatory

Map the filing sequence per market and the evidence each step requires. Follow
`long-job-protocol`.

## Scope

Answers: for a given asset and set of markets, which registration route applies,
what nonclinical / CMC / clinical evidence each filing needs, which expedited routes
may qualify, and which agency meetings gate the program.

Does not cover: legal advice, or the fine design of a single trial (use
`biomed-trial-design`) or CMC package (use `biomed-cmc-quality`). Pathways and
guidance change — cite what you retrieved and its date. This is a regulatory map,
not legal or regulatory advice; confirm with regulatory affairs before filing.

## Workflow

1. **Classify** — Fix modality (small molecule, biologic, cell/gene therapy,
   vaccine), indication, novelty (new chemical/biological entity vs generic /
   biosimilar vs 505(b)(2) reference-reliant), and target markets. Write to
   `outputs/plan/PLAN.md`.
   **Done when:** PLAN.md states modality, novelty class, and markets.

2. **Map the route per agency** — For each market in scope, name the route and its
   filing sequence, citing the governing regulation/guidance (source order below).
   Save fetched bodies to `outputs/mcp/<server>/<call>.json`; failures to
   `outputs/exceptions/regulatory.csv`.
   **Done when:** every market has a cited route and filing sequence.

3. **List evidence per filing** — For each filing, list the nonclinical, CMC, and
   clinical evidence it needs, plus market-specific asks (local data, MRCT,
   bridging). Write to `outputs/research/regulatory/<market>.md`.
   **Done when:** each filing has an evidence checklist with citations.

4. **Expedited routes and interactions** — State each expedited route's qualifying
   criteria (do not assume eligibility) and map the agency-interaction milestones.
   **Done when:** eligibility criteria and meeting milestones are cited.

5. **Compose** — Write `outputs/markdown/regulatory-map.md` per market with the
   evidence gaps and open questions.
   **Done when:** the map covers every market and flags superseded guidance.

## Route reference (name the route, then cite the current guidance)

- **FDA** — commercial IND → marketing application: **NDA 505(b)(1)** (full),
  **505(b)(2)** (relies on data the applicant did not generate), **ANDA**
  (generics), **BLA 351(a)** (biologics), **351(k)** (biosimilars). Expedited
  programs: Fast Track, Breakthrough Therapy, Accelerated Approval, Priority
  Review; Orphan Drug designation is separate. Meetings: pre-IND, End-of-Phase-2,
  pre-NDA/BLA.
- **NMPA (China)** — IND → NDA for 化学药 / 生物制品; the acceptance number (受理号)
  tracks the application. Expedited: 突破性治疗药物, 附条件批准, 优先审评审批, 特别审批;
  沟通交流会议 gate the program.
- **EMA (EU)** — CTA (per the Clinical Trials Regulation) → **MAA** (centralised
  procedure); PRIME for priority medicines, conditional MA, accelerated assessment;
  orphan designation. Scientific Advice / protocol assistance gate the program.

## ICH series (refer to the right series)

- **Q** — quality (e.g. Q1 stability, Q3 impurities, Q8–Q12 development and
  lifecycle).
- **E** — efficacy / clinical (E6 GCP, E8 general considerations, E9 statistics,
  E9(R1) estimands, E10 choice of control, E17 multi-regional trials).
- **S** — safety / nonclinical (toxicology, genotoxicity, carcinogenicity).
- **M** — multidisciplinary (M3 nonclinical timing for clinical trials, M4 the
  CTD, M7 mutagenic impurities).

Name a series only when certain of the mapping; otherwise retrieve and cite.

## Evidence grading

- Regulation, agency guidance, or agency meeting minutes (primary) > agency FAQ >
  consultant summary or news (secondary). Cite the document and its date.
- Guidance is revised and withdrawn. State the issue date and flag anything that may
  be superseded; do not present an old guidance as current.
- Keep agencies separate — FDA precedent does not bind NMPA or EMA.
- Distinguish "no guidance found" from "no requirement exists".

## Output

`outputs/markdown/regulatory-map.md`:
- Asset classification
- Per-market pathway (route, filing sequence, citation)
- Evidence checklist per filing (nonclinical / CMC / clinical / local)
- Expedited-route eligibility (criteria, cited)
- Agency-interaction milestones
- Evidence gaps and open questions
- Disclaimer

`outputs/normalized/filings.csv`:
`market,route,filing,evidence_domain,requirement,citation,guidance_date`.

## Rules

- If `SCENARIO.md` names a Word template, fill that file. Do not invent a parallel markdown report.
- Cite the guidance or regulation behind every requirement, with its date. Do not
  state a requirement from memory.
- Never invent document numbers, designation names, review clocks, or approval
  dates.
- Do not assert any specific drug's current approval status — describe the route and
  cite what you retrieved.
- This is a regulatory map, not legal advice.
