---
name: tax-bank-ledger
description: Merge multi-bank statements (多银行流水/对账单) and the enterprise 银行日记账 into one normalized ledger, then build a 银行余额调节表 per account that proves 企业账面余额 and 银行对账单余额 tie after 未达账项. Use for 多银行流水, 银行对账, 余额调节表, bank rollup, bank reconciliation, or balance reconciliation.
---

# tax-bank-ledger

Normalize every bank file into one ledger, then reconcile each account with a
proper 银行余额调节表. Use `document-ingest`. Keep the
original currency and memo. Never infer a missing balance and never net an
unexplained difference to zero.

## Inputs contract

Required:
- Bank statements (银行对账单 / 流水) per account, as `.xlsx`, `.csv`, digital
  `.pdf`, or scans.

Strongly preferred (needed for reconciliation, not just rollup):
- The enterprise 银行存款日记账 / 账面记录 for the same accounts and period.

Optional:
- An account list (银行, 账号, 币种, 期初余额) to validate coverage.

With statements only, you can produce the unified ledger and per-account rollup
but **not** a 调节表 — say so and report the book side as unavailable. If a
statement is a scan, mark it `needs_vision` and reconcile the accounts that did
parse; do not block the batch.

## Phases

1. **plan** — Write `outputs/PLAN.md`:每个 银行/账号, the date range, the
   expected columns per bank, and whether a book side exists. Done when every
   account and its source files are listed.
2. **ingest** — Run `document-ingest` on all statements and the book ledger. Done
   when every file has a MANIFEST row.
3. **normalize** — Map each bank's own column names onto the unified schema and
   write `outputs/normalized/bank_ledger.csv`. Done when every parsed line is a
   row tagged with its `source` (对账单 or 日记账).
4. **reconcile** — Per account per period, classify 未达账项 and build the 调节表;
   write `outputs/normalized/bank_recon.csv` and `outputs/exceptions/bank_unmatched.csv`.
   Done when every account has a 调节表 row.
5. **compose** — Roll up by 银行 and by month, list accounts that did not tie, and
   write to `outputs/markdown/`. Done when the rollup ties to `bank_ledger.csv`.
6. **review** — Re-check opening/closing continuity and every non-tying account.
   Done when each break is explained or raised as blocking.

## Normalization

Each bank formats statements differently. Map onto one schema and keep the raw
memo verbatim — do not translate or shorten it. Record 收/付 as separate
借方发生额 (存入) and 贷方发生额 (支取) columns; do not collapse them into a signed
number, because sign conventions differ across banks.

**Continuity check** per account per period: `期初余额 + Σ借方 − Σ贷方 = 期末余额`.
If it does not hold, or statement days are missing, raise it — a broken running
balance means the statement is incomplete, not that you should back-fill it.

## Reconciliation logic (银行余额调节表)

Compare the enterprise 账面余额 with the 银行对账单余额 at period end. The two
rarely match on the day; the difference is 未达账项 in exactly four categories:

1. **企业已收、银行未收** — enterprise recorded the receipt, bank has not yet. Add
   to the bank side.
2. **企业已付、银行未付** — enterprise recorded the payment, bank has not yet.
   Subtract from the bank side.
3. **银行已收、企业未收** — bank credited (e.g. 利息收入), enterprise has not
   recorded it. Add to the book side.
4. **银行已付、企业未付** — bank debited (e.g. 手续费, 扣款), enterprise has not
   recorded it. Subtract from the book side.

Then compute:

- `调节后企业余额 = 企业账面余额 + 银行已收企业未收 − 银行已付企业未付`
- `调节后银行余额 = 银行对账单余额 + 企业已收银行未收 − 企业已付银行未付`

The reconciliation **closes only when 调节后企业余额 = 调节后银行余额** (within
±0.01). If they differ, the remaining gap is unexplained — record it in
`bank_unmatched.csv` with `category = unexplained` and mark the account as not
tying. Do not adjust either balance to force a match.

Match book lines to bank lines by amount + date (±3 days) + memo/对方户名; an
unmatched item is a 未达 candidate, classified into one of the four categories by
which side recorded it.

## Output contract

`outputs/normalized/bank_ledger.csv`:
`account_id, 银行, 账号, 币种, 交易日期, 摘要, 对方户名, 对方账号, 借方发生额,
贷方发生额, 余额, 凭证号, source(对账单/日记账), file_id`

`outputs/normalized/bank_recon.csv`:
`account_id, 银行, 账号, 币种, period, 企业账面余额, 银行对账单余额,
银行已收企业未收, 银行已付企业未付, 企业已收银行未收, 企业已付银行未付,
调节后企业余额, 调节后银行余额, 是否调平(Y/N), 剩余差异`

`outputs/exceptions/bank_unmatched.csv`:
`account_id, side(book/bank), 交易日期, 摘要, 金额, category, matched_ref, detail`
where `category` is one of the four 未达 types or `unexplained` / `continuity_break`
/ `missing_days`.

The `outputs/markdown/` report shows: coverage (banks, accounts, days); the
per-bank and monthly rollup; every account that did not tie with its remaining
difference; and the `needs_vision` backlog.

## Rules

- If `SCENARIO.md` names a Word template, fill that file. Do not invent a parallel markdown report.
- State both sides and the difference for every account. A recon with one side is
  not a recon.
- Keep 币种 per line; never sum across currencies. Roll up per currency.
- An unexplained difference blocks the account. Record it; do not zero it out.
- Do not infer a missing opening or closing balance.
- Hand the tied ledger to `tax-closing-checklist` (银行 module) and use
  `tax-recon-supplier` for the payables side of large 对方户名 flows.
