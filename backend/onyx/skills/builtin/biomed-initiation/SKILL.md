---
name: biomed-initiation
description: Orchestrate a full drug-program initiation (立项) report that fans out to the six biomed sub-skills and composes a cited go/no-go memo under an explicit decision framework. Use for 立项, 立项报告, 靶点评估, 项目决策, target brief, target product profile, go/no-go, or program initiation.
---

# biomed-initiation

Run a multi-source 立项 assessment and write a cited go/no-go memo. This is the
orchestrator; it fans out to the six biomed sub-skills. Follow `long-job-protocol`;
parse supplied files with `document-ingest`.

## Scope

Answers: should the program advance — on a defined 靶点, 适应症, modality, and
geography — and on what evidence. Composes literature, clinical, IP, CMC,
regulatory, and (where relevant) trial-design inputs into one decision memo.

Does not cover: the deep single-domain analyses themselves — it delegates those.
This is R&D decision support, not medical, legal, or regulatory advice.

## Workflow

1. **Plan** — Fix the target product profile (TPP): 靶点, 适应症, modality,
   geography, differentiation hypothesis, and the decision question. Write the
   outline and the sub-skill assignment to `outputs/plan/PLAN.md`; seed
   `outputs/plan/TODO.json` with one task per sub-skill.
   **Done when:** PLAN.md holds the TPP and the six assignments.

2. **Fan out** — Give each sub-skill a closed question list; each writes to its own
   `outputs/research/<role>/` notes and normalized CSVs (do not re-do their work
   here):
   - `biomed-literature` → target validation, MoA, biomarker → `research/literature/`
   - `biomed-clinical-intel` → competitive pipeline, readouts → `research/clinical/`
   - `biomed-patent-fto` → IP / FTO position → `research/fto/`
   - `biomed-cmc-quality` → manufacturability, quality risk → `research/cmc/`
   - `biomed-regulatory` → pathway and evidence bar → `research/regulatory/`
   - `biomed-trial-design` → feasibility of the pivotal design, when in scope →
     `research/trial-design/`
   **Done when:** every in-scope role has notes with citations.

3. **Score** — Apply the decision framework below; record a rating and the evidence
   per dimension in `outputs/normalized/decision-matrix.csv`.
   **Done when:** every dimension has a rating and a citation.

4. **Compose** — Write `outputs/markdown/initiation-report.md` with an explicit
   go / no-go / conditional recommendation and the conditions.
   **Done when:** the memo states a recommendation tied to the matrix.

5. **Review** — Check for invented identifiers, uncited claims, and unresolved gaps;
   list them.
   **Done when:** the open-questions list is complete and no claim is uncited.

## Decision framework (score each; cite the evidence)

- **Unmet medical need** — burden, current standard of care, and its gaps.
- **Scientific rationale / 靶点 validation** — strength of the target–disease link
  (genetics, mechanism, translational data).
- **Differentiation** — the TPP advantage over the leading competitor programs.
- **Competitive intensity** — how crowded the mechanism × phase landscape is.
- **Clinical feasibility** — endpoint acceptability and enrollment feasibility.
- **Regulatory pathway** — route clarity, expedited eligibility, evidence bar.
- **CMC feasibility** — manufacturability and quality risk.
- **IP / FTO** — own-position strength and blocking-art exposure.
- **Commercial** — addressable population and access outlook (state assumptions).

Rate each: **supports / neutral / against / unknown**. An "unknown" that gates the
decision becomes a named diligence action, not a guess.

## Evidence grading

- Carry each sub-skill's primary-vs-secondary grading through to the memo; do not
  launder a preprint or a press release into a settled input.
- A dimension with only secondary evidence is rated no higher than **neutral**.
- Distinguish "no evidence found" from "evidence against". A go decision resting on
  the absence of contrary evidence is a conditional go with diligence, not a go.
- The recommendation states which single finding would flip it.

## Output

`outputs/markdown/initiation-report.md`:
- Executive summary and recommendation (go / no-go / conditional)
- TPP and decision question
- Findings per dimension (cited, from the sub-skill notes)
- Decision matrix
- Key risks and the conditions for a conditional go
- Diligence actions for every gating unknown
- Sources
- Disclaimer

`outputs/normalized/decision-matrix.csv`:
`dimension,rating,evidence_summary,citation,gating`.

If the user names a report template in `SCENARIO.md`, follow that structure instead
of the default order.

## Rules

- If `SCENARIO.md` names a Word template, fill that file. Do not invent a parallel markdown report.
- Cite PMID, NCT/CTR, patent numbers, guidance, and 受理号/文号 only from records a
  sub-skill actually fetched. Never invent identifiers, effect sizes, or approval
  dates.
- Do not overrule a sub-skill's "unavailable" with a memory-based claim.
- The memo must state a recommendation and its conditions; a memo with no decision
  is incomplete.
- This is R&D decision support, not medical, legal, or regulatory advice.
