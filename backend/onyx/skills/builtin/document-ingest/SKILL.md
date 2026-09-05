---
name: document-ingest
description: Parse project and library files into MANIFEST plus extracted JSON and CSV. Use for xlsx, csv, pdf, docx, pptx, or scanned images before analysis.
---

# document-ingest

Turn source files into structured extracts. Prefer code over the model.

## Command

Run from the session root:

```
python .opencode/skills/document-ingest/scripts/ingest.py \
  --roots project user_library attachments \
  --out outputs
```

Useful flags:

- `--roots` — directories to scan (default: `project`, `user_library`, `attachments`)
- `--out` — workspace outputs dir (default: `outputs`)
- `--dry-run` — write nothing; print the planned MANIFEST
- `--limit N` — process at most N new files

## What it writes

- `outputs/ingest/MANIFEST.json` — file id, path, parser, status, confidence, error
- `outputs/extracted/<file_id>.json` — tables, text preview, page count
- `outputs/exceptions/ingest.csv` — failed or skipped files
- `outputs/ingest/pages/<file_id>-pNNNN.png` — page images for scanned PDFs

## Parser choice

| Kind | Parser | Model? |
| --- | --- | --- |
| `.xlsx` `.xls` `.csv` | pandas / openpyxl | No |
| Digital PDF with text | pdfplumber | No |
| `.docx` | python-docx | No |
| `.pptx` | python-pptx | No |
| Scanned PDF / image | `pdftoppm` pages + status `needs_vision` | Yes, later, 1–4 pages per batch |

Do not send a `needs_vision` page set to the parent in one shot. Spawn a short
subagent or a later turn. Write each batch to `outputs/extracted/<file_id>.json`
under `pages`.

## After ingest

Read `MANIFEST.json` and `exceptions/ingest.csv`. Continue analysis only from
`extracted/` and `normalized/`. Leave raw files on disk.
