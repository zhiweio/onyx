---
name: long-job-protocol
description: Shared file layout and phase rules for Craft long jobs. Use for multi-turn reports, recon, ingest, or any task that must survive a turn budget.
---

# long-job-protocol

Keep long work on disk so a later turn can continue without the prior context.

## Layout

| Path | Role |
| --- | --- |
| `outputs/plan/PLAN.json` | Source plan: goal, phases, done_when, lanes |
| `outputs/plan/PLAN.md` | Human render of the plan |
| `outputs/plan/TODO.json` | Cross-turn checklist |
| `outputs/plan/PHASE_DONE` | Single line: finished phase id |
| `outputs/ingest/MANIFEST.json` | One row per source file |
| `project/research/<role>/FINDINGS.md` | Specialist notes with citations |
| `project/extracted/` | Extracted tables |
| `outputs/mcp/<server>/<call>.json` | Raw MCP bodies |
| `outputs/exceptions/*.csv` | Failures and exceptions |
| `outputs/markdown/` | Final report |

## Rules

1. Start a turn by reading `PLAN.json` and `TODO.json`. Do not restart from memory.
2. Pull tables with the `document-ingest` skill. Do not paste a whole Excel file into chat.
3. After an MCP call, if the body is large, confirm it landed under `outputs/mcp/` and keep only a digest in the reply.
4. Give subagents a closed question list. Tell them to write files as they go.
5. When the current phase meets its done-when, write `outputs/plan/PHASE_DONE` with that phase id and stop. Do not start the next phase in the same turn unless the user asked for a single-turn job.
