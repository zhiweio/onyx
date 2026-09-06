---
name: meeting-notes
description: Turn a transcript, recording notes, or raw jottings into minutes a non-attendee can act on, separating decisions from actions from open questions. Use for 会议纪要, 纪要, 会议记录, 行动项, 待办, minutes, recap, action items, or follow-ups.
---

# meeting-notes

Turn raw meeting material into minutes someone who was not there can act on.

## Scope

Answers: what was decided, who owes what by when, and what is still open.

Does not cover: transcription itself, or producing the final formatted document
(use `docx` when the user wants a Word file).

## Workflow

1. **Read it all first** — Read the whole source before writing anything.
   Minutes written incrementally mis-rank importance, because the decision often
   arrives after the discussion that motivated it.
   **Done when:** the meeting date, attendees, and stated purpose are identified,
   or explicitly recorded as absent from the source.

2. **Classify every substantive line** into exactly one of four buckets:

   | Bucket | Test |
   | --- | --- |
   | **Decision** | The group settled it. Someone could act on it without asking again. |
   | **Action** | A person owes specific work. Has, or needs, an owner and a date. |
   | **Context** | Background that explains a decision or action. |
   | **Open question** | Raised, not resolved. Needs a named person to close it. |

   A line that sounds like agreement but leaves the choice open is an open
   question, not a decision. "We should probably do X" is not a decision.
   **Done when:** every substantive line is in one bucket.

3. **Complete the actions** — Every action needs an owner, a verb, and a date.
   When the source does not supply one, write `owner: 未指定` or `due: 未确定`
   and add a matching open question. Never invent an owner or a deadline.
   **Done when:** no action is missing an owner or date without a matching open
   question.

4. **Write the minutes** in this order, unless `SCENARIO.md` names a report
   template — then follow that structure.
   1. Meeting, date, duration, attendees (and notable absentees if stated)
   2. Decisions
   3. Action items — owner, due date, action
   4. Discussion summary, grouped by topic
   5. Disagreements, recorded as separate positions
   6. Open questions, each with who will close it

   **Done when:** each section exists, or is marked "none recorded".

## Rules

- If `SCENARIO.md` names a Word template, fill that file. Do not invent a parallel markdown report.
- Record only what the source says. Do not infer a decision from discussion, and
  do not upgrade a suggestion into a commitment.
- Keep a disagreement visible. Record both positions separately; do not merge
  them into one consensus sentence that nobody said.
- Attribute a statement only when the source attributes it. In a transcript with
  unlabeled speakers, say the speaker is unidentified.
- Write each action as a verb phrase with an object ("Send the revised quote to
  procurement"), not a topic ("Quote").
- Preserve numbers, dates, and names exactly as spoken. Flag a figure the
  speaker hedged ("about 200k") as approximate rather than recording it as firm.
- If the source is partial — a transcript that starts mid-sentence, an audio gap,
  a section marked inaudible — say which part is missing and do not fill it.
- Distinguish a decision that was made from one that was deferred; a deferral is
  an open question with a date.
