---
name: tax-recon-supplier
description: Reconcile the 应付账款 ledger against supplier invoices or 供应商对账单, matching on 税号+发票号码 then amount+date with tolerance, and reporting unmatched rows in both directions plus a per-supplier difference summary. Use for 供应商对账, 应付对账, AP reconciliation, invoice-to-ledger match, or payables diff.
---

# tax-recon-supplier

Match the payables ledger to what suppliers billed, and make every difference
explicit. Follow `long-job-protocol` and `document-ingest`. Report unmatched rows
both ways; never net a ledger row against an unrelated invoice to make the total
look right.

## Inputs contract

Required:
- The 应付账款 ledger / 往来明细 (per supplier: 单号/凭证, 日期, 金额, optionally
  税号 and 发票号码).
- Supplier invoices **or** a 供应商对账单 (statement) for the same suppliers and
  period.

Optional:
- 合同 / 采购订单 (PO) for price and quantity comparison.
- A supplier master (供应商编码 ↔ 名称 ↔ 统一社会信用代码).

If one side is missing, stop and ask; you cannot reconcile with a single side. If
a supplier appears on only one side, that is a finding to report, not a reason to
drop the supplier.

## Phases

1. **plan** — Write `outputs/plan/PLAN.md`: the ledger file, the invoice/statement
   source, the suppliers and period in scope, and the match keys available (does
   the ledger carry 税号 and 发票号码, or only 名称+金额?). Done when both sides and
   the key hierarchy are named.
2. **ingest** — Run `document-ingest` on both sides. Route invoice files through
   `tax-invoice-compliance` first when field-level validity matters. Done when both
   sides have MANIFEST rows.
3. **normalize** — Write `outputs/normalized/ap_ledger.csv` and
   `outputs/normalized/ap_billing.csv` with aligned columns and a normalized
   supplier key. Done when both tables share one supplier key.
4. **match** — Apply the key hierarchy, writing matched pairs to
   `outputs/normalized/ap_recon.csv` and the two unmatched files. Done when every
   row on both sides is either matched or in an unmatched file.
5. **compose** — Build the per-supplier summary and write to `outputs/markdown/`.
   Done when 账面 − 对账 = Σ差异 for every supplier.
6. **review** — Spot-check the largest differences against source files. Done when
   each sampled difference is confirmed.

## Match key hierarchy

Try keys in order; stop at the first that matches, and record which key was used:

1. **Exact** — 供应商税号 (统一社会信用代码) + 发票号码. Highest confidence; use
   when the ledger records the invoice number.
2. **Tolerance** — normalized 供应商 + 金额 (2 decimals) + 日期 within ±3 天, then
   widen to ±7 天 on a second pass for the still-unmatched.
3. **Fuzzy** — normalized 供应商 name + amount within tolerance, no reliable date.
   Mark `match_method = fuzzy` and a lower `match_confidence`; a fuzzy match is a
   suggestion for review, not a settled tie.

**Supplier name normalization**: trim spaces, unify 全角/半角, drop bracketed
qualifiers like （中国）, and treat 有限公司 / 股份有限公司 / 集团 suffixes
consistently — but keep the original name in a column. Two legally distinct
entities can share a short name; do not merge on a normalized key alone when 税号
disagrees.

**Amount tolerance**: exact within ±0.01 元; otherwise allow `max(1 元, 0.5%)` and
record the residual as a difference. State the tolerance you used.

## Difference classification

For each matched pair, classify the residual so a human knows what to chase:

- `timing` (未达) — recorded in different periods; amount agrees.
- `price` (价差) — unit price differs vs 合同/PO.
- `quantity` (量差) — quantity differs.
- `tax_rate` (税率差) — 不含税 agrees but 税额/税率 differs.
- `currency` (币种) — different 币种 or FX rate.
- `partial` — one invoice paid across several ledger rows, or one payment covers
  several invoices (many-to-one). Link all legs under one `match_id`.
- `duplicate` (重复) — same 发票号码 matched twice.

Unmatched rows go to their own files: **缺票** (ledger row with no invoice) and
**多票** (invoice with no ledger row). These are the two directions that must
never be silently netted against each other.

## Output contract

`outputs/normalized/ap_recon.csv`:
`match_id, 供应商名称, 供应商税号, ledger_ref, invoice_ref, 账面金额, 对账金额,
差异, 差异类型, match_method(exact/tolerance/fuzzy), match_confidence`

`outputs/exceptions/ap_unmatched_ledger.csv` (缺票):
`供应商名称, 供应商税号, ledger_ref, 日期, 金额, note`

`outputs/exceptions/ap_unmatched_invoice.csv` (多票):
`供应商名称, 供应商税号, invoice_ref, 日期, 金额, note`

The `outputs/markdown/` report leads with a per-supplier table —
`供应商, 账面应付合计, 对账/发票合计, 差异, 差异笔数` — then lists the largest
unmatched items in both directions and the fuzzy matches needing confirmation.

## Rules

- If `SCENARIO.md` names a Word template, fill that file. Do not invent a parallel markdown report.
- Every source row ends up matched or in an unmatched file. Nothing disappears.
- Report both directions separately. Do not offset 缺票 against 多票.
- Per supplier, `账面 − 对账 = Σ差异` must hold; if it does not, you dropped a row.
- Keep 税号 authoritative over name. When 税号 conflicts, do not match.
- Feed the payables view up to `tax-closing-checklist` (往来 module).
