---
name: biomed-literature
description: Build a cited target, mechanism, or competitive-landscape brief from the primary literature, synthesized by theme with graded evidence. Use for 靶点, 机制, 文献综述, 文献检索, 竞品分析, target validation, mechanism of action, biomarker, literature landscape, or systematic search.
optional-mcp:
  - literature-search
  - pharma-intelligence
---

# biomed-literature

Turn a 靶点 / mechanism / 适应症 question into a cited, theme-organized brief.
Parse any supplied files with `document-ingest`.

## Scope

Answers: what is known about a target or mechanism, how strong the evidence is,
which programs pursue it, and what stays unresolved. Covers search design,
retrieval, appraisal, and synthesis.

Does not cover: trial-by-trial competitive pipelines (use `biomed-clinical-intel`),
patent or FTO analysis (use `biomed-patent-fto`), or regulatory pathway mapping
(use `biomed-regulatory`). This is research support, not medical advice.

## Workflow

1. **Scope** — Fix the target, molecule, indication, and species, and the question
   type (target validation, MoA, biomarker, safety signal, landscape). Record the
   date window and out-of-scope items in the notes.
   **Done when:** the search question and inclusion criteria are stated.

2. **Query design** — Build one structured query per database. Separate controlled
   vocabulary (MeSH / Emtree) from free-text `[tiab]` synonyms; join synonyms with
   OR inside a concept, AND across concepts, NOT only to drop a named confound.
   Add species, date, and article-type filters. Record every query string verbatim
   to `outputs/research/literature/queries.md`.
   **Done when:** each planned database has a saved, reproducible query.

3. **Retrieve** — If the host brief names a search MCP (for example
   `parallel-search-382_web_search`), call that tool first. Do not start with
   `webfetch`, OpenCode `websearch`, or bash/`curl`. Use `webfetch` only to
   open a URL the search tool already returned. If a host returns HTTP 403,
   record the miss in `outputs/exceptions/literature.csv` and continue. For
   every hit capture PMID (or DOI / PMCID), title, journal, year, and study
   type. Deduplicate on DOI, then on title+year.
   **Done when:** `outputs/normalized/papers.csv` holds the deduplicated hit set.

4. **Appraise** — Tag each record primary vs secondary and grade it (see Evidence
   grading). Note sample size, model system, and effect direction.
   **Done when:** every row in papers.csv has a study type and a grade.

5. **Synthesize** — Group findings by theme (mechanism, efficacy signal, safety,
   biomarker), not by paper. Where sources conflict, present both and say which is
   better supported. Write `outputs/markdown/literature-brief.md`.
   **Done when:** the brief covers every theme with citations and a gaps section.

## Sources (in order)

1. **PubMed / MEDLINE** — indexed primary literature; the spine of the search.
2. **Europe PMC / PMC** — full text and preprint linkage.
3. **Embase, Cochrane** — pharma coverage and systematic reviews, when available.
4. **Preprint servers (bioRxiv, medRxiv)** — earliest signal; carry a DOI but are
   not peer-reviewed. Label them and weight them down.
5. **Chinese databases (CNKI 知网, 万方)** — domestic work absent from PubMed.
6. **Agency scientific reviews** — FDA review packages, EMA EPARs, NMPA/CDE
   technical reviews carry regulator-appraised primary data; they outrank journals
   for what a regulator actually accepted.

A citation must carry: identifier (PMID or DOI), title, journal/source, year, and
study type. A claim with no retrievable identifier is not a citation.

## Evidence grading

- **Hierarchy** (strong → weak): systematic review / meta-analysis of RCTs > RCT >
  prospective cohort > case-control > case series / mechanistic in vitro > preprint
  / opinion / narrative review.
- **Primary vs secondary** — an original study reports its own data; a review
  reports others'. Never cite a review as the source of a primary result; trace it
  to the original and cite that.
- **No evidence found is not evidence of absence.** State which searches you ran
  and what they returned. Absence in your search set is a search result, not a
  biological fact.
- **Confidence** — raises with independent replication, larger or pre-registered
  studies, human over animal data, and convergent mechanisms. Say which single
  study or dataset would change the conclusion.

## Output

`outputs/markdown/literature-brief.md`:
- Question and search scope (with the date window)
- Key findings by theme, each cited
- Strength of evidence per theme
- Conflicts and how you weighted them
- Gaps — what the literature does not establish
- Sources (full list, with grade)

`outputs/normalized/papers.csv`:
`pmid,doi,title,journal,year,study_type,grade,theme,note`.

## Rules

- If `SCENARIO.md` names a Word template, fill that file. Do not invent a parallel markdown report.
- Cite every material claim with a real PMID or DOI you retrieved. Never invent
  PMIDs, DOIs, author lists, or effect sizes.
- Report an unfetchable source as unavailable; do not fill the gap from memory.
- Keep the gaps section. A brief with no gaps is usually incomplete.
- Do not upgrade a preprint or a single animal study into a settled fact.
