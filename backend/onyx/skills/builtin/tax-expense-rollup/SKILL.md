---
name: tax-expense-rollup
description: Consolidate subsidiary or departmental 报销单/expense claims (docx/xlsx/pdf/scan) into one normalized table and a target template, pivot by 公司 x 部门 x 费用类别, and flag missing-invoice, duplicate, over-standard, and unapproved outliers. Use for 报销汇总, 费用归集, 多主体报销, expense rollup, multi-entity expense, or claim consolidation.
---

# tax-expense-rollup

Pull many expense claims into one table, fill the target template, and surface the
claims a reviewer should look at. Use `document-ingest`.
Use `xlsx` to read and write workbooks; use `tax-invoice-compliance` for the
attached 发票, do not re-validate invoices here.

## Inputs contract

Required:
- Expense claims (报销单) as `.xlsx`, `.docx`, `.pdf`, or scans, usually one file
  per 主体 or per 员工.

Strongly preferred:
- The target consolidation template (its exact column set), so the rollup maps
  onto the fields finance actually uses.

Optional:
- 费用政策 / 标准 (差旅、招待、福利 标准) for over-standard checks.
- A 主体 ↔ 部门 ↔ 员工 master.

If there is no template, define one from the fields below and say you did. If a
claim is a scan, mark it `needs_vision` and roll up the rest; never drop a claim
because it did not parse.

## Phases

1. **plan** — Write `outputs/PLAN.md`: the claim roots, the target template
   fields, and which policy standards are available. Done when every template
   field maps to a claim field (or is marked derived / missing).
2. **ingest** — Run `document-ingest`. Done when every claim file has a MANIFEST
   row.
3. **normalize** — Write `outputs/normalized/expenses.csv`, one row per claim
   **line** (not per form), using the schema below. Done when Σ line 价税合计 per
   form equals the form total.
4. **check** — Apply outlier rules, writing `outputs/exceptions/expense_exceptions.csv`.
   Done when every line has been through the rules.
5. **compose** — Fill the template with `xlsx`, build the 公司×部门×类别 pivot, and
   write both plus the report to `outputs/markdown/` and `outputs/`. Done when the
   pivot total equals Σ `expenses.csv` 价税合计.
6. **review** — Confirm the claim count against `MANIFEST.json` and re-check the
   top outliers. Done when counts tie and outliers are confirmed.

## Normalization

Map every claim onto one line schema, keeping the original 摘要 verbatim and the
original 主体/部门 strings. Split 价税合计 into 金额 (不含税) and 税额 when the
claim shows them; if only the total is shown, record 金额 = 价税合计 and leave 税额
blank rather than back-computing a rate you cannot see. Classify each line into a
费用类别 (差旅费, 交通费, 业务招待费, 办公费, 会议费, 职工福利费, 通讯费, ...); an
unmappable line is `CATEGORY_UNMAPPED`, not force-fit.

## Outlier and policy checks

Raise, but never auto-adjust:

- `MISSING_INVOICE` — a reimbursable line with no 发票号码 / 附件.
- `DUP_INVOICE` — the same 发票号码 across two claims or two lines.
- `NO_APPROVAL` — 审批状态 not approved but included in the rollup.
- `WEEKEND_HOLIDAY` — 差旅/招待 dated on a rest day (a prompt, not a verdict).
- `ROUND_NUMBER` — suspiciously round amounts clustered by one 员工.
- `OVER_STANDARD` — above a supplied 标准 (差旅日标准, 会议费, etc.).
- `LIMIT_WATCH` — categories that commonly hit a CIT 税前扣除限额, notably
  业务招待费 and 职工福利费. **This rollup is a book-level consolidation; the actual
  税前扣除限额 is computed at 汇算清缴, not here.** Recent well-known limits (for
  example 业务招待费 often the lower of 发生额×60% and 营业收入×0.5%, 职工福利费 often
  工资薪金总额×14%) must be **verified against the current rule** before you cite
  one — flag the category for review, do not assert the percentage as settled.

## Output contract

`outputs/normalized/expenses.csv`:
`file_id, 主体, 部门, 员工, 报销单号, 报销日期, 费用类别, 摘要, 金额, 税额,
价税合计, 发票号码, 币种, 审批状态, source(docx/xlsx/pdf/scan), extract_confidence`

`outputs/exceptions/expense_exceptions.csv`:
`file_id, 报销单号, exception_code, severity(block/warn/info), field, detail,
amount, source_ref, needs_vision`

Deliverables in `outputs/`: the filled template workbook; a
`公司 × 部门 × 费用类别` pivot; and a `outputs/markdown/` report with total by
主体, by 类别, the outlier list with amounts, and the `needs_vision` backlog.

## Rules

- If `SCENARIO.md` names a Word template, fill that file. Do not invent a parallel markdown report.
- One claim line is one row. Keep 主体 and 部门 from the source; do not re-bucket.
- Do not invent a missing invoice number, amount, or approver.
- Keep 币种 per line; roll up per currency and never sum across currencies.
- Over-standard and limit flags are review prompts. State the standard you used.
- The pivot total must equal the sum of the normalized lines; if not, a row was
  dropped or double-counted — find it before composing.
