---
name: biomed-trial-design
description: Review or draft the core design of a clinical trial — estimand, population, endpoints, control, randomization, multiplicity, interim analyses, and sample size — with every statistical input sourced. Use for 临床试验设计, 方案设计, 入排标准, 主要终点, 样本量, 非劣效, endpoints, non-inferiority, sample size, or protocol review.
---

# biomed-trial-design

Review or draft the design elements that decide whether a trial can answer its
question.

## Scope

Answers: can the design test the stated question with controlled error and a
credible sample size, and what must change if not. Covers estimand, PICO,
endpoints, control, randomization, multiplicity, interim analyses, and sample-size
inputs.

Does not cover: the competitive trial landscape (use `biomed-clinical-intel`) or the
regulatory acceptability ruling (use `biomed-regulatory`, and confirm with the
agency). This is a design review, not medical advice or a regulatory commitment.

## Workflow

1. **Frame the question** — Write the **estimand** (ICH E9(R1)): treatment,
   population, endpoint (variable), intercurrent-event strategy, and population-level
   summary; then the **PICO** (population, intervention, comparator, outcome, time).
   Save to `outputs/PLAN.md`.
   **Done when:** PLAN.md states one estimand and its PICO.

2. **Work each element** — Assess population, endpoints, control, randomization /
   blinding, statistics, and duration against the checklist below. Write findings to
   `outputs/research/trial-design/review.md`; put every sample-size input in
   `outputs/normalized/ssr-inputs.csv` with its source.
   **Done when:** every element has a verdict and every stat input has a source.

3. **Compare to precedent** — Use `biomed-clinical-intel` to find how accepted
   trials in the indication framed endpoints, comparator, and margin.
   **Done when:** the design is benchmarked against at least one precedent, cited.

4. **Compose** — Write `outputs/markdown/trial-design-review.md`: each element, the
   risk it carries, and the required change.
   **Done when:** every element is reported with a risk and, where needed, a fix.

## Element checklist

- **Population** — inclusion / exclusion, biomarker or enrichment strategy, and
  whether the enrolled population matches the intended label. Over-enrichment
  threatens generalizability; a loose population dilutes the effect.
- **Endpoints** — primary, key secondary (alpha-protected), secondary, exploratory.
  State each endpoint's **validation status**: an established endpoint vs a
  **surrogate** that needs validation (a surrogate supports accelerated approval
  only when accepted for the setting). The primary endpoint must test the estimand
  and match the label claim.
- **Control and hypothesis** — placebo, active, or standard of care, and whether it
  reflects current practice. Distinguish **superiority** from **non-inferiority**: an
  NI margin must be **pre-specified and justified** (it preserves a defined fraction
  of the active control's established effect, and needs an assay-sensitivity
  argument). An NI design with an unjustified margin is the design's core weakness.
- **Randomization and blinding** — allocation method, stratification factors,
  allocation concealment, and blinding level (double-blind vs open-label with
  blinded endpoint / PROBE).
- **Multiplicity** — control the family-wise type I error across multiple endpoints,
  doses, timepoints, subgroups, and interim looks. Name the strategy (hierarchical /
  gatekeeping, Bonferroni / Holm, graphical). An added analysis or endpoint switch
  with no multiplicity control inflates type I error — flag it.
- **Interim analyses** — group-sequential design with an **alpha-spending** function
  (e.g. O'Brien-Fleming or Pocock boundaries via Lan-DeMets), pre-specified efficacy
  and futility boundaries, and an independent DSMB/IDMC. Unplanned looks spend alpha.
- **Sample size** — every input must be sourced: treatment-effect assumption,
  variance or control event rate, one- or two-sided alpha, power, allocation ratio,
  dropout, and accrual. An effect-size assumption with no source is the biggest risk
  to the trial — say so, and do not compute an N without stating every input.
- **Duration** — treatment and follow-up long enough for the endpoint to accrue.

## Common failure modes

Underpowered from an optimistic effect size; wrong or outdated comparator;
unvalidated surrogate as primary; NI margin too wide or set post hoc; multiplicity
uncontrolled; a primary endpoint that does not match the label claim; intercurrent
events ignored (no estimand); enrollment infeasible for the target N.

## Evidence grading

- A sourced assumption (prior RCT, meta-analysis, natural-history dataset) beats an
  expert guess; a pilot or single-arm estimate is weak and usually optimistic.
- Distinguish "endpoint not yet validated" from "endpoint invalid".
- Confidence rises when the effect size comes from a comparable randomized
  population, not a cross-study comparison.

## Output

`outputs/markdown/trial-design-review.md`:
- Estimand and PICO
- Element-by-element review (element, verdict, risk, required change)
- Statistical assumptions with sources
- Precedent comparison
- Top design risks
- Disclaimer

`outputs/normalized/ssr-inputs.csv`:
`input,value,source,note`.

## Rules

- If `SCENARIO.md` names a Word template, fill that file. Do not invent a parallel markdown report.
- Every effect-size or event-rate assumption cites its source; an unsourced one is
  the trial's biggest risk — say so.
- Never invent trial IDs, published effect sizes, or agency positions.
- Flag any change that inflates type I error without multiplicity control.
- Do not compute a sample size without stating every input used.
- This is a design review, not medical advice or a regulatory commitment.
