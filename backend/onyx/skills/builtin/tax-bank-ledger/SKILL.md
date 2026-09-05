---
name: tax-bank-ledger
description: Merge multi-bank statements into one ledger. Use for 多银行流水, bank rollup, or balance reconciliation.
---

# tax-bank-ledger

Normalize bank files into one ledger. Follow `long-job-protocol` and `document-ingest`.

## Phases

1. **plan** — list banks, date range, and expected columns
2. **ingest** — parse each xlsx/pdf statement
3. **analyze** — map columns to date, amount, balance, memo; write `outputs/normalized/bank_ledger.csv`
4. **compose** — rollup by bank and month; note missing days
5. **review** — check opening and closing balances

Keep source currency and original memo. Do not infer missing balances.
