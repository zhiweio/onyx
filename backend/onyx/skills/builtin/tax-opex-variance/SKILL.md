---
name: tax-opex-variance
description: Compare departmental operating expense across periods on a normalized 费用 table, computing 同比 (YoY) and 环比 (MoM) against stated base periods, attributing each material move to a source line, and listing unexplained moves separately. Use for 费用波动, 费用分析, 同比, 环比, opex variance, YoY, or MoM expense analysis.
---

# tax-opex-variance

Explain why operating expense moved between periods, using only moves you can tie
to a source line. Use `document-ingest`. Use `xlsx` to
read the period workbooks (recalculate first if formulas may be stale). Do not
explain a swing you cannot trace; flag it.

## Inputs contract

Required:
- Expense detail for the periods being compared — 费用明细账, 管理费用/销售费用
  明细, or a management report — carrying 期间, 部门, 科目, 金额.

For each comparison you must know the base:
- **同比 (YoY)** needs the same period one year earlier.
- **环比 (MoM)** needs the immediately preceding period.

Optional:
- A 科目 / 部门 mapping so the same account lines up across periods (accounts get
  renamed and re-coded; a rename is not a real variance).
- Quantity/driver data (headcount, 用量, 单价) for price–volume attribution.

If a base period is missing, say which comparison is therefore blocked; do not
compare against a period you do not have.

## Phases

1. **plan** — Write `outputs/PLAN.md`: the periods, the entities/部门 in
   scope, the comparison type(s), and the materiality threshold. Done when the base
   period for every comparison is named.
2. **ingest** — Run `document-ingest` on the period workbooks. Done when every
   period has a MANIFEST row.
3. **normalize** — Write `outputs/normalized/opex.csv`: one row per
   period × entity × 部门 × 科目. Reconcile totals to each source report. Done when
   Σ per period equals the source total.
4. **analyze** — Compute variances, attribute drivers, and write
   `outputs/normalized/opex_variance.csv` and `outputs/exceptions/opex_unexplained.csv`.
   Done when every material line is either attributed or in the unexplained file.
5. **compose** — Write the report to `outputs/markdown/`, largest moves first.
   Done when the reported moves tie to the variance file.
6. **review** — Re-check that renamed/re-coded accounts were aligned, not double
   counted. Done when the account map is confirmed.

## Variance logic

- **State the base for every number.** Write "环比 vs 2024-05" or "同比 vs
  2023-06" next to each figure. A percentage with no stated base is not a finding.
- `variance = compare_amount − base_amount`; `variance_pct = variance / base_amount`.
- **Guard a zero or near-zero base**: if `base_amount = 0`, the account is 新增
  (`NEW`) — report the absolute amount and leave the percentage as NA, never as a
  huge or infinite ratio. A base that vanished is 停止 (`DROPPED`).
- **Materiality**: a move is material when `|variance|` clears the absolute floor
  **and** `|variance_pct|` clears the relative floor (state both, e.g. ≥ 5 万元 and
  ≥ 10%). Only material moves need attribution; immaterial ones are listed but not
  chased.

## Attribution

Attribute a material move to a driver you can point at — a 供应商, a 子科目, a
一次性事项, a headcount change — with a `driver_source` (the file and line). When
quantity and price are both available, decompose:

- `量差 = (Q_compare − Q_base) × P_base`
- `价差 = (P_compare − P_base) × Q_compare`

so the two sum to the total variance. Most opex is lump-sum; then attribute by the
largest contributing lines within the account rather than a price–volume split.

**A move with no source line is unexplained** — it goes to
`opex_unexplained.csv`, not into a narrative. Do not invent a plausible reason.

## Output contract

`outputs/normalized/opex.csv`:
`period, entity, 部门, 科目编码, 科目名称, 金额, 币种, source_ref`

`outputs/normalized/opex_variance.csv`:
`entity, 部门, 科目, comparison_type(YoY/MoM), base_period, compare_period,
base_amount, compare_amount, variance, variance_pct, driver, driver_source,
material(Y/N), explained(Y/N)`

`outputs/exceptions/opex_unexplained.csv`:
`entity, 部门, 科目, comparison_type, base_period, compare_period, variance,
variance_pct, reason(new_account/dropped_account/base_zero/no_source_line/account_unmapped)`

The `outputs/markdown/` report leads with the largest attributed moves and their
drivers, then the unexplained material moves that need a human, then a note on any
account that could not be aligned across periods.

## Rules

- If `SCENARIO.md` names a Word template, fill that file. Do not invent a parallel markdown report.
- Never compare across mismatched units or currencies. Roll up per currency.
- Never report a variance percentage without its base period.
- A rename or re-code is not a variance — align it, or flag `account_unmapped`.
- Explain only what you can source. An unexplained move is a finding, not a gap to
  paper over. Hand structural expense questions to `data-analysis` and
  book-vs-tax questions to `tax-financial-statement`.
