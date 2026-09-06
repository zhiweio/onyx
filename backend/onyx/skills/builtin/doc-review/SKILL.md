---
name: doc-review
description: Review a document for unsupported claims, structural problems, ambiguity, and mechanics, returning specific located findings ranked by severity. Use for 文档审阅, 审校, 校对, 评审, review this doc, proofread, critique, or redline a draft.
---

# doc-review

Review a draft and return findings a writer can act on. Findings, not a rewrite.

## Scope

Answers: what is wrong with this document, where, why it matters, and what to
change.

Does not cover: writing the document, or verifying external facts beyond what
the document itself supports (use `research-brief` when a claim needs checking
against sources).

## Workflow

1. **Read the whole document first** — Establish purpose, audience, and the
   claim the document is making. If purpose or audience is not stated, write
   down the one you assumed; a review against the wrong audience is noise.
   **Done when:** purpose and audience are stated.

2. **Four passes, in this order.** Order matters — do not fix commas in a
   paragraph that should be deleted.

   1. **Claims** — every factual statement, number, date, and citation. For each:
      does the document support it, does the cited source actually say it, and is
      the number internally consistent with other numbers in the document?
      Check totals against their components. Check that percentages name a
      denominator. Check that every figure and table is referenced in the text
      and that the reference matches what the figure shows.
   2. **Structure** — does the order serve the reader? Is the conclusion findable?
      Is anything missing, duplicated, or in the wrong section? Does each section
      do one job?
   3. **Clarity** — ambiguous pronouns and references, undefined terms and
      acronyms on first use, buried conclusions, sentences carrying two claims,
      and hedging that hides whether a thing is true.
   4. **Mechanics** — grammar, inconsistent terminology for the same concept,
      formatting, numbering, and reference style.

   **Done when:** all four passes are complete over the whole document.

3. **Report** — Each finding gets: location (section and quoted text), what is
   wrong, why it matters, and a suggested fix.
   **Done when:** every finding has all four parts and a severity.

## Severity

| Severity | Meaning |
| --- | --- |
| **Blocking** | Wrong, unsupported, or internally contradictory. Ship this and someone is misled. |
| **Major** | Correct but the reader will likely misunderstand or fail to find it. |
| **Minor** | Mechanics and consistency. |
| **Optional** | A different choice you would make. Explicitly not a defect. |

Sort by severity, not by position in the document. A blocking finding on the
last page outranks a typo on the first.

## Rules

- Separate "this is wrong" from "I would write it differently". Label the second
  kind Optional so the author can ignore it without guilt.
- Do not rewrite the document unless asked. Return findings; suggest replacement
  wording only for the specific span at fault.
- Do not flag a style choice that is applied consistently. Consistency beats your
  preference.
- Quote the exact text you are commenting on so the author can find it.
- When you cannot verify a claim from the document or its cited sources, mark it
  **unverified** rather than calling it wrong, and say what would verify it.
- Review a template as a template: assess the placeholders and the structure, not
  the sample values filling them.
- If the document is a draft fragment, say what appears missing rather than
  reviewing it as if complete.
