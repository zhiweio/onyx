---
name: tax-invoice-compliance
description: Check a batch of Chinese VAT invoices (增值税专用发票/普通发票, 电子发票, OFD/XML/PDF/扫描件) for required fields, 纳税人识别号 format, 税率 plausibility, 税额与价税合计重算, 三流一致, 红字/作废 handling, and duplicates, then emit a per-issue exception list. Use for 发票合规, 发票审核, 查验, invoice compliance, invoice validation, or invoice exception lists.
---

# tax-invoice-compliance

Turn a pile of invoices into one exception list a 财务/税务 reviewer can act on.
Prefer code and rules over the model. Follow `long-job-protocol` for the phase
layout and `document-ingest` for parsing. Never invent a 发票号码, 税号, amount,
or 校验码 — if a value cannot be read, record it as missing, not guessed.

## Inputs contract

Required:
- One or more invoice files (`.pdf` 版式文件, `.ofd`, `.xml` 电子发票, or scans).

Optional, used only when present:
- 合同 / 采购订单 (for 三流一致 buyer/seller and item checks).
- 银行流水 / 付款记录 (for 三流一致 payment leg).
- 认证/勾选抵扣清单 or 进项发票台账 (to cross-check deduction status).
- The taxpayer's own 名称 + 统一社会信用代码, so 购/销方 can be判定为进项 or 销项.

If invoices are missing, stop and ask for them. If only scans are supplied, run
the job but mark every scanned file `needs_vision`; do not fail the whole batch
because one file will not parse.

## Phases

1. **plan** — Write `outputs/plan/PLAN.md`: the invoice roots, the reporting
   period, the taxpayer's own 税号, and which optional cross-checks are possible
   given the files present. Done when the plan lists every input path.
2. **ingest** — Run `document-ingest`. Digital PDF/OFD/XML parse with code; scans
   land as `needs_vision` in `outputs/ingest/MANIFEST.json`. Done when every input
   file has a MANIFEST row (parsed or `needs_vision`).
3. **normalize** — Write `outputs/normalized/invoices.csv`, one row per invoice,
   using the schema below. Keep original strings; do not reformat 日期 or 金额.
   Done when every parsed invoice is a row.
4. **check** — Apply the rule set to each row, writing
   `outputs/exceptions/invoice_compliance.csv`, one row per issue. Done when every
   invoice has been through every applicable rule.
5. **compose** — Write the report to `outputs/markdown/`. Done when the summary
   counts tie to the exception file.
6. **review** — Re-read a sample of blocking exceptions against the source
   extract. Done when each sampled issue is confirmed or corrected.

For scanned files, extract the fields in a short subagent or later turn (1–4 pages
per batch) and merge into `invoices.csv`; do not push a whole page set to the
parent at once.

## Field and format checks

Per invoice, confirm the required fields exist and are well-formed:

- **发票代码 / 发票号码** — present; 号码 typically 8 digits, 代码 10 or 12 digits
  for older formats. 全面数字化电子发票 ("数电票") carries only a 20-digit 发票号码
  and no 代码 — treat a missing 代码 as normal for 数电票, not an error.
- **开票日期** — present, parseable, and inside the reporting period. A date outside
  the period is `DATE_OUT_OF_PERIOD`.
- **购买方 / 销售方 名称与纳税人识别号** — 税号 must be a valid 统一社会信用代码
  (18 位, 数字+大写字母) or a legacy 15/17/20-位 纳税人识别号. Bad shape is
  `TAXID_FORMAT`. For 专用发票 the buyer 税号 is mandatory.
- **金额, 税率, 税额, 价税合计** — all present and numeric.
- **校验码** — for 普通发票, the last-six-digits 校验码 should be present.

## Amount and rate logic

- **税额重算** — recompute `金额 × 税率` and compare with the printed 税额. Allow a
  rounding tolerance of ±0.01 元 per line. A larger gap is `TAX_MISCALC`.
- **价税合计** — must equal `金额 + 税额` within ±0.01 元, else `TOTAL_MISMATCH`.
- **税率 plausibility** — check the 税率 against the bands that apply to the 业务类型.
  As of writing, Chinese VAT commonly uses 13% / 9% / 6% 税率 and 3% / 5% 征收率,
  plus 0%/免税 — **verify the current bands and the rate for this业务 before flagging**;
  do not assert a rate table as current fact. A 税率 outside every plausible band,
  or one that does not fit the item (for example 13% on a 交通运输 line, which is
  usually 9%), is `RATE_IMPLAUSIBLE` — a flag for review, not an assertion of error.

## Three-flow and status checks

- **三流一致** — when 合同 and 付款记录 are present, the 合同 counterparty, the
  发票 购/销方, and the 收/付款 account should be the same legal entity. A break is
  `THREE_FLOW_MISMATCH`; state which of the three legs disagrees.
- **红字发票** — negative-amount 红字 invoices must reference an original 蓝字发票
  (对应蓝字发票代码/号码 or 红字信息表编号). A 红票 with no reference is
  `REDLETTER_NO_REF`.
- **作废 / 冲红** — an invoice marked 作废 or fully 红冲 must not be counted as a
  valid 进项/销项. Counting one is `VOID_COUNTED`.
- **重复** — the same 发票代码+号码 (or 数电票号码) appearing twice is `DUP_INVOICE`;
  report both file_ids.
- **抵扣时限** — deduction-window rules have been relaxed in recent years (the
  认证确认期限 for general taxpayers was removed). Do not assert a fixed number of
  days or a 文号; when a 进项 invoice looks aged, raise `DEDUCT_WINDOW` as a review
  note and say the current rule must be confirmed.

## Output contract

`outputs/normalized/invoices.csv`:
`file_id, invoice_kind, 发票代码, 发票号码, 开票日期, 购买方名称, 购买方税号,
销售方名称, 销售方税号, 项目摘要, 金额, 税率, 税额, 价税合计, 校验码, 开票人,
方向(进项/销项), 状态(正常/作废/红冲), 来源(digital/xml/ofd/scan), extract_confidence`

`outputs/exceptions/invoice_compliance.csv`:
`file_id, 发票号码, exception_code, severity(block/warn/info), field, expected,
actual, detail, source_ref, needs_vision`

Exception codes: `MISSING_FIELD`, `TAXID_FORMAT`, `TAXID_MISMATCH_HEADER`,
`RATE_IMPLAUSIBLE`, `TAX_MISCALC`, `TOTAL_MISMATCH`, `DUP_INVOICE`,
`THREE_FLOW_MISMATCH`, `VOID_COUNTED`, `REDLETTER_NO_REF`, `DATE_OUT_OF_PERIOD`,
`DEDUCT_WINDOW`, `SCAN_NEEDS_VISION`, `LOW_CONF_EXTRACT`.

The `outputs/markdown/` report contains: scope and period; counts by
`exception_code` and by `severity`; the blocking issues first with amounts; the
`needs_vision` backlog; and the plausibility flags that a human must confirm.

## Rules

- If `SCENARIO.md` names a Word template, fill that file. Do not invent a parallel markdown report.
- One issue is one row. A single invoice may produce several exception rows.
- Never stop the batch because one file failed; record it and continue.
- Severity `block` for anything that makes an invoice non-deductible or the batch
  untrustworthy (bad 税号, 作废 counted, 重复, 税额/合计 mismatch); `warn` for
  plausibility flags; `info` for readable-but-noteworthy items.
- Rate and time-limit flags are review prompts, not verdicts. Say so in `detail`.
- Hand invoice-level results up to `tax-expense-rollup` (报销发票) and
  `tax-recon-supplier` (供应商发票) rather than re-parsing there.
