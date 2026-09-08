---
name: biomed-clinical-initiation
description: Write a cited clinical-stage initiation report for any modality already in human trials (Phase I to NDA or post-approval expansion). Covers patient pool, competitor landscape, clinical benchmarking, probability of success, registration path, patent and LOE intelligence, deals, dual-scenario sales, cost and return, TPP, risk matrix, and go/no-go. Use for 临床期立项, 临床立项报告, 开发策略, in-license 评估, PoS, 销售预测, 交易评估, or clinical-stage asset diligence.
---

# biomed-clinical-initiation

Turn a clinical-stage asset into a cited initiation report. Do evidence
work first, then judgment, then the report. Parse uploaded files with
`document-ingest`.

This skill does not give FTO, infringement, clinical, regulatory, tox, or
investment advice. A patent attorney must clear any launch or FTO decision.

## Scope

Answers: whether a program already in human trials should advance, expand
a line or indication, or be in-licensed — and on what evidence. Covers
patient-pool math, competitor timing, clinical benchmarking, probability
of success (PoS), registration path, patent/LOE intelligence, deals,
dual-scenario sales, remaining cost and return, TPP, risk matrix, and a
three-state go / conditional-go / no-go.

Covers any modality once human data exist: small molecule, antibody,
bispecific, ADC/DAC, cell or gene therapy, RNA, and post-approval
expansion. Typical uses: start a pivotal study, expand a line, assess an
in-license, or monitor a late-stage competitor.

Does not cover: a preclinical ADC/DAC sequence and payload brief (use
`biomed-adc-dac-initiation`); a generic early 立项 orchestrator (use
`biomed-initiation`); trial-by-trial pipeline only (use
`biomed-clinical-intel`); claim-level FTO only (use `biomed-patent-fto`).

## Public retrieval (no vendor lock)

Do **not** name a commercial pipeline, deal, or patent-intelligence
product, a server id, or a tool slug. Do **not** call a private capture
or replay helper.

Discover tools from **this session**:

1. Prefer an installed MCP tool whose **name** contains `web_search` or
   `search` and whose schema takes an objective plus queries.
2. Call that search tool **first** for every public hunt (literature,
   trials, approvals, patents, deals, epidemiology, news).
3. Use `webfetch` only for (a) a URL the search tool already returned, or
   (b) a known public scientific or regulator API listed below.
4. Do not start with OpenCode `websearch`, bash, or `curl`.
5. If no search MCP is installed, record that in
   `outputs/exceptions/clinical-initiation.csv` and continue with
   `webfetch` to the public APIs. Never fill gaps from model memory.

Write every query string to
`outputs/research/clinical-initiation/queries.md`. Persist hit lists and
fetched metadata under `outputs/normalized/` and notes under
`outputs/research/clinical-initiation/`. Read those files when writing;
do not rely on truncated chat previews.

### Public databases (precise match)

Use structured queries. Prefer identifier lookup (PMID, NCT/CTR, patent
number with kind code, approval number) over a broad web sweep.

| Need | Primary public source | Typical match key |
| --- | --- | --- |
| Papers / abstracts | PubMed eutils, Europe PMC | PMID, DOI, TITLE+AUTH |
| Preprints | Europe PMC, bioRxiv / medRxiv | DOI |
| Trials | ClinicalTrials.gov, ChiCTR, EU CTR, WHO ICTRP | NCT / CTR / EUCT |
| Trial results | CT.gov results, PubMed papers, company IR | NCT + PMID |
| Labels / approvals | DailyMed, Drugs@FDA, Orange Book, Purple Book, EMA EPAR, NMPA/CDE notices | proper name, 受理号 |
| Guidelines / SoC | NCCN, CSCO, ESMO, CACA public pages | indication + line |
| Epidemiology | GLOBOCAN, SEER, published epi papers, national registries | ICD / histology |
| Patents / families | Espacenet, WIPO PATENTSCOPE, USPTO Patent Public Search, CNIPA, Google Patents | PN + kind (`A1`/`B2`) |
| Deals / BD | Company 8-K, HKEX/SSE filings, IR pages, press (then verify) | party + date |
| Pricing / access clues | Public NRDL lists, tender notices, label price footnotes | product + year |

Converge the indication to a **biomarker + line of therapy** (for example
1L DLBCL, R/R FL after PI3K) so the core competitor set stays near ~100
records. Do not page a huge unfiltered list.

Layer depth:

- **Detail** — the asset, 5–10 benchmarks, and any record that enters a
  report table: follow identifiers until the record is complete.
- **Count** — landscape size, phase mix, or PoS denominators: one
  aggregated or first-page `total` is enough.
- **Lead** — news, meetings, or deal rumors: one or two result pages,
  then switch to an identifier fetch.

Stop a query on empty pages, duplicate pages, or a host 403. Log the
stop reason. A zero-hit literature or registry query must be rewritten
at least once before you abandon it.

Cross-check time-sensitive status three ways: registry record × paper or
label × recent news lead. Prefer the structured source. Mark the as-of
date on every stage, approval, and deal.

## Dual input

User files outrank public hits when they conflict (see source ranks).

| Material | Minimum | If missing |
| --- | --- | --- |
| Drug / sponsor / phase / indication + line | Required at start | Ask once, then stop |
| Decision question (advance / expand / in-license / monitor) | Required | Ask once, then stop |
| Asset CSR / CTA / readout summary | Optional | Use public trial results; mark “needs CSR check” |
| Internal sales or pricing model | Optional | Build dual scenarios from explicit assumptions |
| Remaining R&D budget | Optional | Use published cost ranges; mark the gap |
| Report template | Optional | Use the fourteen-chapter contract below |

Parse attachments with `document-ingest`. Do not invent NCT/CTR IDs,
effect sizes, deal values, or prevalence numbers that are not in a file
or a fetched record.

## Source ranks and IDs

Conflict: keep the higher rank. A lower rank may add context only.

| Rank | Source | Use |
| --- | --- | --- |
| S1 | User CSR/CTA, internal forecast, budget, filing pack | Asset readout, price, remaining cost |
| S2 | Registries, labels, regulator notices, patent office records | Stage, design, result, approval, patent number |
| S3 | Peer-reviewed papers, GLOBOCAN/SEER, formal guidelines | Biology, epidemiology, SoC |
| S4 | Meeting abstracts, company IR, deal announcements | Early signal, disclosed economics |
| S5 | News, aggregators, model knowledge | Leads only — never the sole source of a number |

IDs: `F` uploaded file, `P` patent, `W` public web or API hit, `A`
derived analysis, `I` labeled inference. Number them (`W1`, `A2`).
Every `W` or `P` row must store the URL or accession you fetched.

News is a lead. A material fact from news must be confirmed on an S2
source before it enters the report.

### Competitor-mapping confidence

| Grade | Meaning | Wording |
| --- | --- | --- |
| A | Registry or label ties name, sponsor, and indication | “competitor X is in phase Z” |
| B | Several primary sources agree | “public evidence supports …” |
| C | Alias + sponsor + indication inference | “this report infers …; verify” |
| U | Not enough evidence | “no verifiable record” — leave blank |

## Neutrality (report fails if broken)

1. Do not write marketing words (best-in-class, first-in-class,
   breakthrough, superior, 颠覆, 同类最优) unless you quote a source
   with its ID.
2. Present supporting and contrary evidence in every chapter. Do not
   omit failed trials, terminated programs, or safety warnings.
3. Do not rank results across different designs, populations, endpoints,
   or assessment methods. Place them side by side and state the limit.
4. Mark every derived number (patient pool, share, sales, PoS, cost,
   NPV) with an `A`/`I` ID and an assumption-ledger row. Say “estimate”
   or “scenario”, never mix with disclosed values.
5. Show Base and Best (and Bear if used) with equal weight. Put
   parameter differences in the assumption ledger.
6. Missing data is a named gap. Do not fill it from memory. A published
   industry benchmark needs a `W` ID.
7. Every go/no-go line and every rationale line must point to a source
   ID. Drop or downgrade unsupported claims.

## Workflow

1. **Brief** — Fix the drug (and aliases), sponsor, modality and route,
   current phase and known readouts, target indication + line +
   biomarker slice, decision question, competitor scope, geography,
   forecast window, and data cutoff. Write `outputs/PLAN.md` and seed
   `outputs/TODO.md`.
   **Done when:** those variables are written down.

2. **Inventory** — List uploaded files and public fetches in
   `outputs/normalized/sources.csv`.
   **Done when:** each planned source class has a row or a logged gap.

3. **Retrieve** — Search MCP first, then `webfetch` the APIs above.
   Cover: epidemiology and SoC; approved and investigational
   competitors; key trial designs and readouts; registration precedents;
   patents and LOE windows; disclosed deals; access or pricing clues.
   Write a retrieval-depth table
   (`outputs/normalized/retrieval-depth.csv`) with tool or host, query,
   layer (detail / count / lead), hit count, pages taken, complete
   (yes/no), and stop reason.
   **Done when:** queries.md and the depth table exist, and no detail
   query is incomplete without a stop reason.

4. **Freeze ledgers** — Fill the five tables below before prose.
   **Done when:** every benchmark has a source and a mapping grade;
   every derived number has an assumption row.

5. **Derive** — Patient-pool waterfall, PoS interval, review-time
   stats, dual-scenario sales, remaining cost and simple NPV, risk
   matrix. Register every assumption.
   **Done when:** each derived table cites algorithm, inputs, and
   sample size.

6. **Judge** — Pick a 5–10 competitor benchmark set, a five-line
   rationale (need / efficacy / safety / timing / registrability and
   commerce), a differentiation list, a TPP, and GO / conditional GO /
   NO-GO. Calibrate gates from the best **public** same-indication
   benchmark, not from a fixed generic number.
   **Done when:** the recommendation and its flip-conditions are stated.

7. **Compose** — Write
   `outputs/markdown/clinical-initiation-report.md` (fourteen chapters
   + appendices). If `SCENARIO.md` names a Word template, fill that file
   with the `docx` skill and do not invent a second report.
   **Done when:** the memo states a decision and every material claim
   is cited.

8. **QA** — Check invented IDs, unlabeled inferences, marketing words,
   one-sided evidence, and missing units. List residual gaps.
   **Done when:** the gap list is complete and no claim is uncited.

## Ledgers

`outputs/normalized/sources.csv`:
`source_id,rank,kind,title,identifier,url_or_path,location,used_for,date_checked,notes`.

`outputs/normalized/pipeline.csv`:
`competitor_key,drug,aliases,sponsor,target,indication,line,highest_phase,clinical_ids,expected_readout,deals,registration,patent_window,mapping_grade,source_ids`.

`outputs/normalized/readouts.csv`:
`evidence_id,drug,trial_id,phase,population,endpoint,value,unit,assessment,safety_flags,conditions,source_id,comparability_notes`.

`outputs/normalized/assumptions.csv`:
`assumption_id,analysis,value,basis,scenario,sensitivity`.

`outputs/normalized/risks.csv`:
`risk_id,category,description,probability,impact,evidence,mitigation,monitor`.

`outputs/normalized/retrieval-depth.csv`:
`query_id,host_or_tool,query,layer,hit_count,pages,complete,stop_reason`.

## Ten evidence jobs

Each job: public source → method → output → neutrality → limit.

### 1. Disease, epidemiology, patient pool

Sources: GLOBOCAN / SEER / published epi papers; guidelines for SoC and
unmet need; user files.

Method (must be stepwise, all `A` where derived):

`incidence or prevalence (W, as-of) × population base (W, state the
frame) → all patients → × line / biomarker / prior-therapy fractions
(W or guideline) → addressable pool → × penetration assumption (A) →
peak patients`.

Output: waterfall table (formula, input, source or assumption ID,
output) plus an unmet-need list bound to evidence.

Limit: do not invent prevalence. Missing year or geography is a gap.

### 2. Competitor landscape

Sources: labels and approval notices; trial registries; guideline pages.

Method: (1) approved matrix — who already holds the line; (2) count-layer
phase mix, including terminated or withdrawn history; (3) timing window —
align expected readouts and launches with this asset’s milestone
(`I` if inferred).

Output: approval matrix, pipeline mix, key-trial table (registry ID +
expected readout), timing-alignment table.

Limit: expected readout is the sponsor estimate unless marked actual.
Do not drop a faster competitor.

### 3. Clinical benchmarking

Sources: CT.gov results, papers, user CSR/CTA.

Method: extract design → population (line / marker / N) → endpoint →
value (keep IRC/INV, mPFS/PFS, 95% CI) → safety. Place the asset next
to each benchmark. Do not rank across mismatched methods.

Output: efficacy table and safety table (grade ≥3, discontinuation,
dose change, special warning), each row with source and comparability
note.

Limit: a single-arm or small-N result is downgraded wording. Undisclosed
endpoints stay “not disclosed”.

### 4. Probability of success (PoS)

Sources: count-layer phase × status tallies in the same indication
(optionally same mechanism); detail-layer terminated or withdrawn
cases; reuse readout rows; published industry PoS papers (`W`) as a
reference frame only.

Method (all `A`): phase-transition counts and ratios with N and as-of;
positive vs negative pivotal-style readouts; famous failures and stated
reasons; interval (not a point) from current phase to approval, plus
up/down drivers (mechanism validation, biomarker, last-line to front-line
difficulty).

Output: transition table, signed readout list, failure table, PoS
interval and drivers, method limits (survivor bias, registry lag).

Limit: public sources have **no ready-made PoS field**. Do not present
an industry paper as this asset’s probability.

### 5. Registration path

Sources: NMPA/CDE public notices, Drugs@FDA, EMA EPAR, registry
pivotal-trial records.

Method: same-indication approval precedents (type, review length,
conditional / breakthrough / priority if disclosed); derived
accept-to-approve duration (`A`); inferred milestone axis for this
asset (`I`), anchored to precedents.

Output: precedent table, duration stats, milestone axis.

Limit: meeting minutes and review detail are often unpublished — mark
the gap. Inferred dates are “based on precedents, not a commitment”.

### 6. Patent landscape and FTO intelligence

Sources: public patent offices listed above, keyed by drug or sponsor
plus indication — not a dump of the whole disease.

Method: this asset’s numbers / types / regions / expiry; competitor
LOE windows as sales inputs; expected exclusivity from launch to
expiry; overlapping in-force numbers as FTO *signals* only.

Output: layout table, LOE window table, exclusivity estimate, FTO
signal list.

Limit: stay at number / type / expiry intelligence. **Do not state
freedom-to-operate or infringement.** Full text, families, legal status,
and claims need a patent attorney. Write that gap in appendix D.

### 7. Deals and BD

Sources: company filings and IR; search-MCP news as a lead, then fetch
the filing.

Method: same-target or same-indication licenses, options, M&A, and
collaborations in the last 2–3 years; disclosed upfront / total only;
derived comparable range (`A`) when stage and readout are similar.

Output: deal list, density, comparable range.

Limit: write “not disclosed” when the amount is missing. Do not invent
milestone structures. A quiet market must still be shown.

### 8. Sales and patient-share (two scenarios)

Sources: patient-pool output, timing window, registration axis, LOE
windows, public access clues, user forecast.

Method (all `A`): peak patients → launch timing (`I`) → share ramp
(from timing and differentiation evidence) → annual cost (`A`/`W`) →
yearly sales = patients × share × cost → post-LOE erosion (`A`).
Base and Best are required; Bear is optional. Every parameter sits in
the assumption ledger.

Output: assumption table by scenario, yearly sales and share tables,
peak vs NPV-style peak note.

Limit: **state that no public sales or pricing database is used; every
amount is assumption-driven.** User internal forecasts (`F`) outrank
and are shown beside the derived case.

### 9. Remaining cost and return

Sources: user budget (`F`) first; published same-phase cost ranges
(`W`); sales scenarios.

Method (all `A`): remaining cost by leftover phase (pivotal, extra
studies, filing, launch prep) as an interval; peak-sales / remaining-cost
ratio; simple discounted NPV with an explicit discount rate; payback
year.

Output: cost table, return and NPV scenarios, payback, discount-rate
sensitivity.

Limit: public sources have **no cost database**. Without a budget or a
cited range, downgrade to a framework and list the gap. Do not imply a
certain return.

### 10. Risk matrix

Sources: contrary evidence from the nine jobs above.

Method: register scientific/clinical, registration, commercial,
competitive, and patent risks. Rate probability × impact (`I`, with
reason). Bind mitigation and a monitor (for example a competitor
Phase 3 readout date).

Output: matrix and the risks ledger.

Limit: ratings are judgment. Mitigation that is not evidence-backed is
`I`.

## Decision frame

### Benchmark set

Prefer the most advanced same-line clinical competitors, even when
data are incomplete. Cover more than one mechanism or generation.
Always include the current standard of care. Usually 5–10 assets;
state include and exclude reasons.

### Rationale lines (each needs evidence and contrary evidence)

1. Unmet need at the target line — does this asset answer it?
2. Efficacy versus benchmarks — keep original methods.
3. Safety and tolerability, including combination use.
4. Competitive gap at the expected launch time.
5. Registration clarity and whether the pool plus access can carry a
   commercial scenario.

Write “evidence is insufficient” when a line cannot be closed.

### Differentiation

Answer efficacy, safety, route and adherence, combination fit,
manufacturing or cost (only with evidence), and regional registration
timing. Bind each point to a source. No marketing words.

### TPP

Build effectiveness and safety rows (add route if useful). Each metric
has an assumption value (`A`) and the actual benchmark readout beside
it. The assumption is the minimum bar for a successful filing, not a
forecast. Flag any assumption that beats every historical same-class
readout.

### Go / No-Go (required closing chapter)

Give GO, conditional GO, or NO-GO. Do not leave the decision open;
missing information becomes a condition. A conditional GO lists 3–5
observable de-risking gates with dates. Add a 12–24 month milestone
map (`I`). A GO that rests only on “nothing contrary found” is a
conditional GO with named diligence.

## Fourteen-chapter contract

Industry document format (numbered chapters, tables, footnotes). Not a
slide deck.

1. Executive summary — facts, evidence strength (support and contrary),
   dual-scenario commercial points, PoS interval, go/no-go and
   conditions, gap summary. Readable on one page.
2. Disease, epidemiology, and patient-pool waterfall.
3. Competitors: approved matrix, investigational mix, key trials,
   timing window.
4. Clinical benchmarking (efficacy + safety).
5. PoS: transitions, signed readouts, failures, interval, limits.
6. Registration path: precedents, duration stats, inferred milestones.
7. Patent landscape and FTO intelligence (plus formal-FTO gap).
8. Deals and BD.
9. Sales and patient-share, Base and Best.
10. Remaining cost and return.
11. Rationale lines and differentiation list.
12. TPP versus benchmark readouts.
13. Risk matrix and mitigations.
14. Go/No-Go, conditions, and 12–24 month roadmap.

Appendix A: source register (URL or path for every `W`/`P`/`F`).
Appendix B: retrieval-depth table.
Appendix C: assumption ledger.
Appendix D: data-gap list (no sales database, no ready-made PoS, no
cost database, no patent full text or legal status, any unfetched host).

Put the source ID next to the number in the body. The appendix does not
replace in-line cites.

## Rules

- If `SCENARIO.md` names a Word template, fill that file. Do not invent a
  parallel markdown report.
- Cite PMID, NCT/CTR, patent numbers, approval numbers, and 受理号 only
  from records you fetched. Never invent identifiers, effect sizes,
  deal values, or prevalence.
- Do not treat a news brief as a registration or approval fact.
- Do not write a legal FTO or infringement conclusion.
- Do not present derived sales, PoS, or cost as a database disclosure.
- Report an unfetchable source as unavailable. Do not replace it from
  memory.
- A memo with no decision is incomplete.
- This is R&D decision support, not medical, legal, or regulatory advice.
