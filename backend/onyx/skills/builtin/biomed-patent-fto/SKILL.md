---
name: biomed-patent-fto
description: Build a claim-level freedom-to-operate and patent-landscape brief for a molecule, target, or formulation, mapping families, expiries, exclusivities, and design-arounds. Use for 专利, FTO, 自由实施, 专利布局, 专利到期, freedom to operate, IP landscape, claim mapping, or patent expiry.
mcp-groups:
  zhihuiya-patent:
    - patsnap-search
    - patent-briefing
    - patsnap-analytics
    - patent-landscape
    - patent-analysis
    - patent-value
    - patent-status
default-mcp-group: zhihuiya-patent
---

# biomed-patent-fto

Map the patents that could block or enable a contemplated product, claim by claim.
Cite source files. Do not invent a patent number.

## Scope

Answers: which patent families read on a contemplated product; when the blocking
claims expire per jurisdiction; what regulatory exclusivities run in parallel; and
where a design-around exists.

Does not cover: infringement opinions, validity opinions, or licensing terms.
**FTO output here is an engineering and strategy input, not legal advice.** A
qualified patent attorney must clear any launch decision.

## Workflow

1. **Define the product** — Fix the compound (and salt / polymorph), formulation,
   dose, indication (method of use), process, and target jurisdictions.
   **Done when:** each product feature a claim could read on is listed.

2. **Search** — Query the sources below by compound, target, assignee, and
   classification (IPC/CPC, e.g. A61K). If a **Patsnap MCP** server is configured,
   query it for families and legal status; if not, use public registers and state
   that the commercial feed is missing. Log dead ends to
   `outputs/exceptions/patent.csv`.
   **Done when:** the candidate family set is saved to
   `outputs/normalized/families.csv`.

3. **Map claims** — For each family, read the independent claims and map them
   feature-by-feature against the product definition. Classify claim type:
   composition of matter (compound), salt / polymorph / crystalline form,
   formulation, method of use (indication or dosing regimen), or process. Mark
   read-on: yes / partial / no, with the reason. Write to
   `outputs/research/fto/claim-map.md`.
   **Done when:** every candidate family has a claim type and a read-on verdict.

4. **Expiry and exclusivity** — For each blocking family, compute the base term and
   add extensions and exclusivities as SEPARATE concepts (see below), per
   jurisdiction.
   **Done when:** each blocking family has a per-jurisdiction expiry line.

5. **Design-around and compose** — For each blocking claim, state whether a
   non-infringing alternative exists (different salt, formulation, route, or
   indication). Write `outputs/markdown/fto-brief.md`.
   **Done when:** every blocking claim has a design-around note and the legal
   disclaimer is present.

## Identifier and date discipline

- **Publication vs grant** — an application publication (kind `A1`/`A2`; US
  `US2020xxxxxxxA1`, PCT `WO2020xxxxxxA1`) is not enforceable; a granted patent
  (kind `B1`/`B2`; `US10xxxxxxxB2`, `EP...B1`, `CN...B`) is. Never treat a pending
  application as a granted block.
- **Family** — distinguish the **simple / DOCDB family** (same priority) from the
  broader **INPADOC family**. Analyze at family level; a US block usually has EP,
  CN, and JP siblings.
- **Dates** — priority date (starts the 20-year clock), filing date, publication
  date, grant date, and **expiry** = earliest filing + 20 years, adjusted by term
  extensions. Keep them distinct; cite the source register for legal status.
- **Kind codes** are jurisdiction-specific — confirm per office; do not assume US
  conventions elsewhere.

## Term vs exclusivity (keep separate)

- **Patent term** — 20 years from the earliest non-provisional filing.
- **Patent term extension** — US PTE (up to 5 years for regulatory delay) and EU
  **SPC** (up to 5 years) extend a *patent*.
- **Regulatory / data exclusivity** — a *separate* bar granted by the drug
  regulator, independent of any patent (new chemical entity, orphan, and biologic
  exclusivities differ by market). Do not add it to the patent term; report it as a
  parallel timeline and cite the regulator's register (e.g. FDA Orange Book for
  small molecules, Purple Book for biologics; EU/NMPA registers per market).

## Evidence grading

- The official register (USPTO Patent Public Search, EPO Espacenet, WIPO
  PATENTSCOPE, CNIPA) is primary for legal status; a commercial aggregator
  (Patsnap) is a fast index but must be confirmed against the register before any
  expiry is relied on.
- Distinguish "no blocking family found in the searches I ran" from "the product is
  clear" — applications in the 18-month publication blackout are invisible.
- A claim you have read outranks a title/abstract guess; never verdict on a family
  from its title alone.

## Output

`outputs/markdown/fto-brief.md`:
- Product definition
- Blocking-families table (family, assignee, claim type, read-on, expiry per
  jurisdiction)
- Parallel regulatory-exclusivity timeline
- Design-around options per blocking claim
- Open questions for counsel
- Legal disclaimer

`outputs/normalized/families.csv`:
`family_id,pub_or_grant,number,kind_code,assignee,claim_type,jurisdiction,priority_date,expiry,read_on,source`.

## Rules

- If `SCENARIO.md` names a Word template, fill that file. Do not invent a parallel markdown report.
- Never invent patent numbers, assignees, priority dates, or expiry dates.
- Never state that a product is "clear" — state what your search covered and did
  not, and refer the decision to counsel.
- Keep publication and grant separate; keep patent term and exclusivity separate.
- Report an empty or unavailable feed as unavailable, not as absence of patents.
