---
name: research-brief
description: Research a topic across retrievable sources and write a cited brief with findings, disagreements, and explicit gaps. Use for 调研, 研究简报, 竞品分析, 市场调研, 背景调研, market scan, background brief, desk research, or literature summary.
---

# research-brief

Produce a cited brief from sources you actually retrieved in this session.
Write intermediate notes to disk when the brief spans more than one turn.

## Scope

Answers: what is known about a question, how strong the evidence is, and what
could not be established.

Does not cover: domain-specific deep dives with their own source hierarchies —
use `biomed-literature`, `biomed-clinical-intel`, `tax-policy-trend`, or
`tax-compliance` when the topic is theirs.

## Workflow

1. **Scope** — Write the question, the time window, the geography, and what is
   explicitly out of scope into `outputs/PLAN.md`. Narrow a broad ask rather
   than answering all of it shallowly; say which narrowing you chose.
   **Done when:** PLAN.md states the question and the exclusions.

2. **Plan the queries** — List the search terms and their variants (synonyms,
   the Chinese and English forms, product vs company vs ticker) before searching.
   Record them so a later turn does not silently repeat or skip a query.
   **Done when:** `outputs/plan/queries.md` lists the planned queries.

3. **Gather** — Use the search and browsing capability available in this session.
   For every source captured: URL, title, publisher, publication date, retrieval
   date, and whether it is primary or secondary.
   **Done when:** `outputs/normalized/sources.csv` has one row per source and
   every row has a URL and a date.

4. **Assess each source** — Apply the hierarchy below. Note who benefits from the
   claim: a vendor's own page is a primary source about its product's marketing
   and a weak source about its market share.
   **Done when:** every source has a tier and a one-line reliability note.

5. **Synthesize by theme, not by source** — Group findings by question, then
   attach the sources that bear on each. A brief organized source-by-source is a
   reading list, not an analysis.
   **Done when:** `outputs/research/brief/findings.md` groups every finding under
   a theme with citations.

6. **Compose** — Write `outputs/markdown/research-brief.md` in the order below,
   unless `SCENARIO.md` names a report template.
   **Done when:** every section exists and every material claim carries a
   citation.

## Source hierarchy

| Tier | Examples | Weight |
| --- | --- | --- |
| Primary official | Regulatory filings, statute and agency publications, court records, standards bodies | Highest — cite the document, not coverage of it |
| Primary organizational | Company filings, annual reports, official announcements, product documentation | High for facts about the issuer; weak for claims about competitors |
| Primary data | Datasets, registries, statistical bureaus, audited figures | High — record the extraction date, since these revise |
| Secondary expert | Peer-reviewed work, industry analyst reports, textbooks | Medium — check the underlying source |
| Secondary reporting | News, trade press, blogs | Low — use to find primaries, not as the citation |
| Unattributed | Aggregator summaries, forum posts, undated pages | Do not cite as fact |

When two sources disagree, prefer the higher tier, the more recent, and the one
closer to the underlying data — and report that they disagree.

## Report structure

1. Question and scope, including exclusions
2. Summary — three to five findings, each able to stand alone
3. Findings by theme, each with citations
4. Disagreements — where sources conflict and which is better supported
5. Gaps — what could not be established and what would establish it
6. Sources — the table from `sources.csv`
7. Suggested next steps

## Rules

- If `SCENARIO.md` names a Word template, fill that file. Do not invent a parallel markdown report.
- Cite every material claim with a URL and a date. A claim with no citation must
  be labelled as your inference.
- Never present secondary reporting as a primary source. If you could not reach
  the primary, say so.
- If a search returns nothing useful, record that source as unavailable. Do not
  fill the gap from memory — an unsourced fact is the failure mode this skill
  exists to prevent.
- Distinguish **no evidence found** from **evidence of absence**, explicitly.
- Date-stamp anything that changes (prices, headcounts, market positions,
  regulatory status) with both the source date and the retrieval date.
- Keep the gaps section. A brief with no gaps is almost always an incomplete
  brief that hid them.
- Do not invent URLs, titles, authors, dates, or figures.
