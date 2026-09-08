---
name: biomed-cmc-quality
description: Assess CMC and quality risk for a drug substance or product against ICH quality guidelines, pharmacopeias, labels, and recall/inspection records. Use for CMC, 药学, 质量研究, 杂质, 稳定性, 工艺验证, impurities, degradants, stability, shelf life, container closure, or inspection/recall risk.
---

# biomed-cmc-quality

Assess pharmaceutical-quality risk and map each risk to the governing guideline.
Parse supplied dossiers with `document-ingest`.

## Scope

Answers: what quality risks apply to a drug substance (原料药/API) and drug product
(制剂) — impurities, stability, container-closure, process robustness — which
ICH/pharmacopeial requirement governs each, and what recall and inspection history
signals.

Does not cover: clinical efficacy/safety, or the regulatory filing sequence (use
`biomed-regulatory`). Do not assert a specific product's current specification or
label content — retrieve and cite it.

## Workflow

1. **Scope** — Fix the modality (small molecule, peptide, biologic, cell/gene),
   dosage form, route, and manufacturing region.
   **Done when:** drug-substance and drug-product scope are separated.

2. **Gather** — Retrieve the governing guidelines, the pharmacopeial monograph, the
   approved label, and any recall/inspection records (source order below). If the
   host brief names a search MCP, call that tool first. Ingest supplied dossier
   files to `outputs/extracted/`; log failures to `outputs/exceptions/cmc.csv`.
   **Done when:** each in-scope attribute has a cited governing document.

3. **Assess by attribute** — Work the checklist below. For each critical quality
   attribute (CQA) state the risk, the driver, and the controlling guideline. Write
   findings to `outputs/research/cmc/findings.md` and one risk row per attribute to
   `outputs/normalized/cmc-risk.csv`.
   **Done when:** every CQA has a risk level and a citation.

4. **Compose** — Write `outputs/markdown/cmc-quality-brief.md` with prioritized
   risks and recommended next checks.
   **Done when:** the brief ranks risks and lists the open CMC questions.

## Attribute checklist (map each to its guideline)

- **Drug substance vs drug product** — assess separately; CQAs and specifications
  differ.
- **Impurities and degradants** — organic impurities (ICH Q3A drug substance /
  Q3B drug product), residual solvents (Q3C), elemental impurities (Q3D). Treat
  **mutagenic (genotoxic) impurities** under **ICH M7** as a distinct, higher-tier
  concern: DNA-reactive species controlled to a toxicological threshold, not an
  ordinary impurity.
- **Specifications and methods** — Q6A (small molecule) / Q6B (biologic);
  analytical validation Q2; analytical procedure development Q14.
- **Stability and shelf life** — Q1A (stability testing), Q1B (photostability),
  Q1E (data evaluation). Derive the shelf-life or retest period and the storage
  statement from the stability data and climatic zone, not from assumption.
- **Container-closure and E&L** — closure-integrity, extractables and leachables,
  especially for parenterals and biologics.
- **Process and control strategy** — process validation and lifecycle: Q8
  (pharmaceutical development / QbD), Q9 (quality risk management), Q10 (quality
  system), Q11 (drug-substance development), Q12 (lifecycle management); GMP for
  APIs is Q7.
- **Biologics add** — Q5A–Q5E (viral safety, comparability, cell substrates,
  stability of biotech products).

Refer to a guideline by series and topic only when you are certain of the mapping
(e.g. Q1A = stability, Q3D = elemental impurities, M7 = mutagenic impurities);
otherwise retrieve and cite it.

## Evidence grading

- Governing guideline, pharmacopeial monograph, or approved label (primary) >
  manufacturer white paper > secondary commentary. Cite the issuing body and
  document.
- A recall or inspection finding (FDA Enforcement Report, warning letter / Form
  483, EudraGMDP, NMPA notice) is primary evidence of a realized failure; a single
  finding is a signal, not a base rate — say so.
- Distinguish "no recall found in the databases I searched" from "the process is
  robust".

## Output

`outputs/markdown/cmc-quality-brief.md`:
- Scope (modality, form, region)
- Risk by attribute (attribute, risk level, driver, governing guideline, citation)
- Recall / inspection signals
- Recommended next checks
- Sources

`outputs/normalized/cmc-risk.csv`:
`attribute,substance_or_product,risk_level,driver,governing_guideline,citation`.

## Rules

- If `SCENARIO.md` names a Word template, fill that file. Do not invent a parallel markdown report.
- Cite every material claim with an issuing body and document; never invent
  impurity limits, batch numbers, inspection outcomes, or shelf-life figures.
- Do not state a specific product's current specification or label from memory —
  retrieve it.
- Every risk level (high / medium / low) must have a stated driver.
- Report an unreachable source as unavailable.
