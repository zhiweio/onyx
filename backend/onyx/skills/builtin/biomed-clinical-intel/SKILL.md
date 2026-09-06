---
name: biomed-clinical-intel
description: Map the clinical pipeline and competing trials for an indication or asset by mechanism and phase, with readout timing and enrollment feasibility. Use for 临床, 管线, 竞争格局, 竞品临床, 临床试验登记, ClinicalTrials, pipeline scan, competitive trials, readout timing, or enrollment feasibility.
---

# biomed-clinical-intel

Build a cited scan of who runs what trial, at what phase, with which design, and
when it reads out. Follow `long-job-protocol`.

## Scope

Answers: the competitive clinical pipeline for a 适应症 or asset class, grouped by
mechanism and phase; how competitor trials are designed; when key readouts and
completions are expected; and how feasible enrollment looks.

Does not cover: single-trial design critique (use `biomed-trial-design`), the
approval pathway (use `biomed-regulatory`), or preclinical literature (use
`biomed-literature`). Registry data is self-reported and often stale — treat it as
a lead, not truth.

## Workflow

1. **Scope** — Fix indication, mechanism/target, phase range, and geography. Write
   to `outputs/plan/PLAN.md`; seed `outputs/plan/TODO.json`.
   **Done when:** PLAN.md names the indication and the mechanisms in scope.

2. **Search registries** — Query each registry in the source order below with
   condition + intervention + mechanism terms. Save raw result bodies to
   `outputs/mcp/<server>/<call>.json`; unfetchable pages to
   `outputs/exceptions/clinical.csv`.
   **Done when:** every in-scope registry has been queried and logged.

3. **Extract** — One row per trial in `outputs/normalized/trials.csv`. Capture the
   registry ID exactly (see Identifier formats), sponsor, phase, status,
   target/mechanism, line of therapy, N, primary endpoint, start date, and
   primary-completion date.
   **Done when:** every trial has a valid registry ID and a primary endpoint.

4. **Analyze** — Cluster by mechanism × phase; flag the most advanced program per
   mechanism; compare endpoints and comparators across competitors; estimate
   readout timing from primary-completion dates; judge enrollment feasibility
   (target N vs eligible population, and the count of trials competing for the same
   patients). Write notes to `outputs/research/clinical/analysis.md`.
   **Done when:** each mechanism cluster has a lead program and a readout estimate.

5. **Compose** — Write `outputs/markdown/clinical-intel.md`.
   **Done when:** the report covers every cluster with cited trials and a
   feasibility read.

## Identifier formats

- **ClinicalTrials.gov** — `NCT` + 8 digits (e.g. NCT00000000). The global default.
- **China 药物临床试验登记与信息公示平台** (chinadrugtrials.org.cn) — `CTR` + 8 digits
  (登记号/公示号). The authoritative China source.
- **EU** — CTIS trial number (post-2022) and legacy **EudraCT** `YYYY-NNNNNN-NN`.
- **Other national** — ISRCTN, jRCT (Japan), CTRI (India), ANZCTR; the WHO ICTRP
  aggregates them.

Cite each trial by its registry ID and the registry, never by sponsor PR alone.

## Analytical content

- **Phase semantics** — Phase 1 (safety / PK / dose), Phase 2 (proof of concept,
  dose-finding), Phase 3 (confirmatory), Phase 4 (post-marketing). A Phase 1/2 or
  2/3 is seamless; note it.
- **Status** — recruiting, active-not-recruiting, completed, terminated, withdrawn,
  suspended. A terminated Phase 3 in the indication is a signal; find and state the
  disclosed reason.
- **Readout timing** — estimate from the primary-completion date, not the
  study-completion date; note that dates are sponsor estimates and slip.
- **Enrollment feasibility** — compare target N to the addressable population and to
  competing trials recruiting the same line of therapy; heavy overlap slows
  everyone.
- **Design comparison** — line up primary endpoint, comparator, and randomization
  across the leading competitors; a differentiated endpoint or comparator is the
  competitive story.

## Evidence grading

- Registry record (primary) > sponsor pipeline page > press release > news
  aggregator (secondary). Prefer the registry; use PR only for what registries omit
  and label it sponsor-sourced.
- Distinguish "no trial found in the registries I searched" from "no such program
  exists" — undisclosed and early programs are invisible.
- A result posted on the registry or published outranks a top-line press release.

## Output

`outputs/markdown/clinical-intel.md`:
- Scope (indication, mechanisms, geography, date)
- Landscape table: mechanism × phase, lead program each
- Competitor design comparison
- Readout calendar (trial, estimated readout, source)
- Enrollment-feasibility read
- Gaps and sources

`outputs/normalized/trials.csv`:
`registry_id,registry,sponsor,phase,status,target,line,n,primary_endpoint,start,primary_completion,source_url`.

## Rules

- If `SCENARIO.md` names a Word template, fill that file. Do not invent a parallel markdown report.
- Never invent NCT / CTR / EudraCT numbers, enrollment counts, or readout dates.
- A date is an estimate unless the record marks it actual; say which.
- Report an unreachable registry as unavailable.
- This is competitive intelligence, not a guarantee of any competitor's plan.
