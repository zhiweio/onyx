---
name: biomed-adc-dac-initiation
description: Write a cited ADC/DAC (antibody-drug or degrader-antibody conjugate) initiation report covering sequence clusters, epitopes, function data, payload rationale, and go/no-go. Use for ADC, DAC, 抗体偶联, 降解剂偶联, 表位, payload, sequence cluster, VH/VL, or ADC/DAC 立项.
---

# biomed-adc-dac-initiation

Turn a new ADC or DAC target into a cited initiation report. Do evidence
work first, then R&D judgment, then the report. Parse uploaded files with
`document-ingest`.

This skill does not give FTO, infringement, clinical, regulatory, tox, or
investment advice. A patent attorney must clear any launch or FTO decision.

## Scope

Answers: whether an ADC/DAC program should start; which antibody lineages,
epitope bins, and payload hypotheses to take forward; and what the next
12–24 months must prove.

Covers early ADC, bispecific ADC, biparatopic ADC, immunotoxin, and DAC
programs when the user has (or the public web can supply) patents, papers,
registries, and optional sequence listings.

Does not cover: a generic small-molecule 立项 (use `biomed-initiation`);
a clinical-stage commercial / PoS / sales report for any modality (use
`biomed-clinical-initiation`); trial-by-trial pipeline only (use
`biomed-clinical-intel`); claim-level FTO only (use `biomed-patent-fto`).

## Public retrieval (no vendor lock)

Do **not** name a commercial patent-intelligence product, a server id, or a
tool slug. Do **not** call a private capture or replay helper.

Discover tools from **this session**:

1. Prefer an installed MCP tool whose **name** contains `web_search` or
   `search` and whose schema takes an objective plus queries.
2. Call that search tool **first** for every public hunt (literature,
   pipeline, patents, meetings, company status).
3. Use `webfetch` only for (a) a URL the search tool already returned, or
   (b) a known public scientific API listed below.
4. Do not start with OpenCode `websearch`, bash, or `curl`.
5. If no search MCP is installed, record that in
   `outputs/exceptions/adc-dac.csv` and continue with `webfetch` to the
   public APIs. Never fill gaps from model memory.

Write every query string to `outputs/research/adc-dac/queries.md`.
Persist hit lists and fetched metadata under `outputs/normalized/` and
notes under `outputs/research/adc-dac/`. Read those files when writing;
do not rely on truncated chat previews.

### Public databases (precise match)

Use structured queries. Prefer identifier lookup (PMID, NCT, patent
number with kind code, UniProt, PDB) over a broad web sweep.

| Need | Primary public source | Typical match key |
| --- | --- | --- |
| Papers / abstracts | PubMed eutils, Europe PMC | PMID, DOI, TITLE+AUTH |
| Preprints | Europe PMC, bioRxiv / medRxiv | DOI |
| Trials | ClinicalTrials.gov, ChiCTR, EU CTR | NCT / CTR / EUCT |
| Patents / families | Espacenet, WIPO PATENTSCOPE, USPTO Patent Public Search, CNIPA, Google Patents | PN + kind (`A1`/`B2`) |
| Sequences | UniProt, NCBI Protein, PDB, IMGT; patent sequence tables when published | accession, SEQ ID |
| Chemistry | PubChem | name / InChI / CID |
| Labels / exclusivity | DailyMed / FDA label, Orange Book, Purple Book, EMA EPAR, NMPA/CDE reviews | proper name |
| Target identity | HGNC, UniProt | gene / protein |

Converge the indication to a **biomarker + line of therapy** (for example
R/R AML, 1L DLBCL non-GCB) so the core competitor set stays near ~100
records. Do not page a huge unfiltered list.

Layer depth:

- **Detail** — assets, patents, and sequences that enter the report:
  follow identifiers until the record is complete.
- **Count** — landscape size or assignee rank: one aggregated or
  first-page `total` is enough.
- **Lead** — meeting abstracts or news: one or two result pages, then
  switch to an identifier fetch.

Stop a query on empty pages, duplicate pages, or a host 403. Log the
stop reason. A zero-hit literature query must be rewritten at least once
before you abandon it.

## Dual input

User files outrank public hits when they conflict (see source ranks).

| Material | Minimum | If missing |
| --- | --- | --- |
| Target / payload / indication | Required at start | Ask once, then stop |
| Antibody table (CSV/XLSX) | Optional | Build the pool from public patent and paper hits |
| Patent PDFs / listings | Optional | Use public full text / sequence tables; mark “needs listing check” |
| Internal KD / IC50 / tox | Optional | Leave as a named gap |
| Report template | Optional | Use the ten-chapter contract below |

Parse attachments with `document-ingest`. Do not invent sequences or
assay numbers that are not in a file or a fetched record.

## Source ranks and IDs

Conflict: keep the higher rank. A lower rank may add context only.

| Rank | Source | Use |
| --- | --- | --- |
| S1 | Sequence listing, patent example tables, paper supplements | VH/VL, SEQ ID, KD, IC50 |
| S2 | Patent body, claims, figures, company technical pages | Design, linker/payload |
| S3 | Peer-reviewed papers, PDB, registries, regulator reviews | Biology, structure, status |
| S4 | Meeting abstracts, posters, investor decks | Early signal |
| S5 | Aggregators, news, model knowledge | Leads only — never the sole source of a sequence or number |

IDs: `F` uploaded file, `P` patent / listing, `W` public web or API hit,
`A` derived analysis, `I` labeled inference. Number them (`W1`, `P2`).
Every `W` or `P` row must store the URL or accession you fetched.

### Candidate–sequence confidence

| Grade | Meaning | Wording |
| --- | --- | --- |
| A | Direct name ↔ SEQ ID | “candidate X uses VH SEQ ID …” |
| B | Several primary sources agree | “public evidence supports …” |
| C | Unique CDR + lineage + function | “this report infers …; verify on listing” |
| D | Same-lineage proxy | “proxy for modeling, not the clinical sequence” |
| U | Not enough evidence | “no verifiable sequence” — leave blank |

Do not pair adjacent SEQ IDs unless the patent states the pair.

## Workflow

1. **Brief** — Fix target (and aliases), species, modality (mAb ADC /
   bispecific / biparatopic / DAC), payload class, indication slice,
   geography, data cutoff, and special focus (sequence, epitope,
   internalization, KO kill, species cross, FTO differentiation).
   Write `outputs/PLAN.md` and seed `outputs/TODO.md`.
   **Done when:** those variables are written down.

2. **Inventory** — List uploaded files and public fetches in
   `outputs/normalized/sources.csv`. Split patent families (priority,
   assignee, role: parent Ab / humanized / ADC / payload / use).
   **Done when:** each priority family has a readable text source or a
   logged gap.

3. **Retrieve** — Search MCP first, then `webfetch` the APIs above.
   Cover: target biology; competitor ADC/DAC programs; patent families;
   antibody sequences; payload chemistry and clinical precedent.
   **Done when:** queries.md exists and each planned source class was
   queried or marked unavailable.

4. **Freeze ledgers** — Fill the three tables below before prose.
   **Done when:** every benchmark antibody has a source and a mapping
   grade; every number has model, unit, condition, and source.

5. **Cluster and epitope** — Deduplicate, global identity, CDR motif,
   hierarchical cluster, E1–E5 epitope layer. Sequence cluster is **not**
   an epitope bin and **not** a legal boundary.
   **Done when:** `outputs/normalized/clusters.csv` exists.

6. **Judge** — Pick a 6–10 antibody pilot set, a TPP, payload rationale,
   five-layer FTO *framework* (sequence / epitope / format / linker-payload
   / use) as an engineering map, and GO / conditional GO / NO-GO.
   Calibrate gates from the best **public** same-target benchmark.
   **Done when:** the recommendation and its flip-condition are stated.

7. **Compose** — Write `outputs/markdown/adc-dac-initiation-report.md`
   (ten chapters + appendices). If `SCENARIO.md` names a Word template,
   fill that file with the `docx` skill and do not invent a second report.
   **Done when:** the memo states a decision and every material claim is
   cited.

8. **QA** — Check invented IDs, unlabeled inferences, cluster-as-epitope
   wording, and missing units. List residual gaps.
   **Done when:** the gap list is complete and no claim is uncited.

## Ledgers

`outputs/normalized/sources.csv`:
`source_id,rank,kind,title,identifier,url_or_path,location,used_for,date_checked,notes`.

`outputs/normalized/sequences.csv`:
`sequence_key,antibody,aliases,chain,seq_type,seq_id,source_id,location,length,pair_id,cdr_scheme,lineage,mapping_grade,cluster_id,qc_flags`.

`outputs/normalized/assays.csv`:
`evidence_id,molecule,assay,model,value,unit,conditions,payload,dar,source_id,directness,claim`.

`outputs/normalized/clusters.csv`:
`cluster_id,members,vh_identity,vl_identity,fv_identity,cdrh3_note,epitope_layer,benchmark`.

Identity: Needleman–Wunsch on normalized VH and VL; identity =
matches / aligned columns (gaps in the denominator). State the CDR
numbering scheme (patent / IMGT / Kabat / Chothia) and do not mix them.

Working hints only: Fv ≥ 90% plus shared CDRs ≈ near lineage; 70–90% ≈
related; below 70% ≈ likely independent. Final bins need CDRH3, germline,
patent origin, and function.

### Epitope layers

| Layer | Evidence | Allowed claim |
| --- | --- | --- |
| E1 | Ab–antigen X-ray / cryo-EM | Contact residues |
| E2 | HDX, alanine/DMS, XL-MS | Hotspots |
| E3 | SPR/BLI/cell competition | Same / overlapping / different bin |
| E4 | Truncation / domain swap | Domain or region |
| E5 | Docking or CDR similarity | Testable hypothesis only |

## Payload module

Answer all seven: intracellular concentration need; linkerable site and
post-release activity; plasma vs endosome vs cytosol release; bystander
vs retained; DAR / hydrophobicity vs PK and uptake; clinical or platform
precedent; target-entry × payload-mechanism intersection.

DAC extra: linker-payload LC-MS; E3 dependence; DC50 / Dmax / recovery;
proteasome dependence and rescue; E3 and antigen density in the cell
context; normal-cell window; non-binding DAC / free payload / naked Ab /
KO / classical ADC controls.

Do not rank IC50 values across different payloads, DAR, cell lines, or
incubation times.

## Ten-chapter contract

1. Executive summary and R&D judgment (GO / conditional GO / NO-GO)
2. Target biology and ADC fit (expression, shedding, internalization,
   normal tissue, species, antigen construct)
3. Competitive and patent-family landscape (status as of the cutoff)
4. Core patents: VH/VL/CDR and assay tables
5. Sequence clusters and the pilot benchmark set
6. Epitope, binning, and structure (E1–E5)
7. Payload mechanism and platform / clinical lessons
8. Differentiated TPP and preclinical matrix
9. Computational and CRO work package (antigen bounds, Fv/full-length,
   structure tasks, assays, priority)
10. Risks, five-layer FTO *map*, Go/No-Go gates, 12–24 month roadmap

Appendix A: key VH/VL/CDR with source and mapping grade.
Appendix B: source register and what each source supports.

Put the source ID next to the number in the body. The appendix does not
replace in-line cites.

## Pilot-set rule

1. Strongest clinical or in-vivo functional benchmark.
2. One medoid (or strongest function) per major sequence cluster.
3. One representative per known competition bin or domain epitope.
4. Best internalization, human/cyno cross, low-antigen kill, and
   developability examples.
5. If payload class differs, keep one same-target classical ADC as a
   platform control.
6. Usually 6–10 antibodies; grow only when clusters or bins require it.

## Rules

- If `SCENARIO.md` names a Word template, fill that file. Do not invent a
  parallel markdown report.
- Cite PMID, NCT/CTR, patent numbers, and accessions only from records
  you fetched. Never invent identifiers, sequences, or effect sizes.
- Do not treat a publication (`A1`) as a granted block (`B2`).
- Do not write a sequence cluster as a known epitope or an FTO conclusion.
- Report an unfetchable source as unavailable. Do not replace it from memory.
- A memo with no decision is incomplete. A GO that rests only on “nothing
  contrary found” is a conditional GO with named diligence.
- This is R&D decision support, not medical, legal, or regulatory advice.
