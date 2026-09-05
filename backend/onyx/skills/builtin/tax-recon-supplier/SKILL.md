---
name: tax-recon-supplier
description: Reconcile supplier payables against invoices or statements. Use for 供应商对账, AP match, or invoice-to-ledger diffs.
---

# tax-recon-supplier

Match payables to invoices. Follow `long-job-protocol` and `document-ingest`.

## Phases

1. **plan** — name the payable file, the invoice folder, and match keys
2. **ingest** — extract ledgers and invoices to `outputs/extracted/`
3. **analyze** — join on tax ID, amount, and date; write `outputs/normalized/recon.csv` and `outputs/exceptions/unmatched.csv`
4. **compose** — report plus the exception list
5. **review** — spot-check large diffs against source files

## Match keys

Prefer 税号 / vendor code, then amount (2 decimals), then date (±3 days).
Record unmatched rows. Do not drop them.
