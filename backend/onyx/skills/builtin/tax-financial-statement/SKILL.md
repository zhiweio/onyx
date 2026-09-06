---
name: tax-financial-statement
description: Analyze the 资产负债表, 利润表, and 现金流量表 together, prove 三表勾稽, compute ratios with their exact 取数科目, compare 同比/环比 against stated base periods, and note 税会差异 caveats. Use for 财务报表分析, 三表勾稽, 资产负债表, 利润表, 现金流量表, financial statement analysis, or ratio analysis.
---

# tax-financial-statement

Read the three statements as one system and report what drives the numbers, not
just the numbers. Follow `long-job-protocol` for multi-round work. Use `xlsx` to
read workbook inputs — recalculate first when formulas may be stale, because
`openpyxl` does not compute formulas. State the basis before any figure.

## Inputs contract

Required:
- 资产负债表 (BS), 利润表 (IS), and 现金流量表 (CFS) for the period.

Strongly preferred:
- 所有者权益变动表 and 财务报表附注 (for 勾稽 and drivers).
- The 科目余额表 (to trace a ratio back to accounts).
- A prior period (同比 needs last year; 环比 needs the preceding period).

Always establish, and state up front: reporting period, 币种, unit (元 / 千元 /
万元), and accounting standard (企业会计准则 / IFRS / US GAAP). If a statement is
missing or partial, name which analysis is therefore blocked instead of filling
the gap.

## Phases

1. **plan** — Write `outputs/plan/PLAN.md`: the statements present, the periods,
   the basis (unit/币种/准则), and the questions to answer. Done when the basis is
   fixed and the comparison periods are named.
2. **ingest** — Run `document-ingest` / `xlsx` on the statements. Done when every
   statement is a parsed extract.
3. **tie** — Check the 勾稽 relationships below and write
   `outputs/exceptions/statement_ties.csv` for any break. Done when each relation
   is confirmed or logged as a break.
4. **ratios** — Compute the ratios that answer the question and write
   `outputs/normalized/ratios.csv`. Done when every ratio names its formula and
   取数科目.
5. **compose** — Write findings to `outputs/markdown/`, leading with the answer.
   Done when every stated movement names its driver line.
6. **review** — Re-check that no unit/period was mixed and that each break was
   reported, not worked around. Done when the ties file and ratios file agree with
   the narrative.

## 三表勾稽 (tie the statements)

Confirm these before analyzing; report a break rather than adjusting around it:

- **会计恒等式** — `资产总计 = 负债合计 + 所有者权益合计` on the BS.
- **净利润 → 未分配利润** — `期末未分配利润 = 期初未分配利润 + 本期净利润 −
  提取盈余公积 − 分配股利`. The IS 净利润 must flow into the equity movement.
- **现金勾稽** — CFS `期末现金及现金等价物余额` must equal BS `货币资金` 期末,
  **after** removing amounts that are not cash equivalents (受限资金, 保证金, 定期
  存款 > 3 个月). State the reconciling items; a raw equality that ignores them is a
  false tie.
- **CFS 补充资料** — 净利润 adjusted for 折旧摊销, 资产减值, 财务费用, and the
  changes in 经营性应收/应付/存货 should reconcile to 经营活动现金流量净额.
  折旧摊销 should tie to the 累计折旧/摊销 movement; the working-capital adjustments
  should tie to the BS line movements.
- **权益变动表** — its 期初/期末 columns tie to the BS 所有者权益.

## Ratios (name the formula and the 取数科目)

Write each ratio with its exact source lines. Common set:

- 资产负债率 = `负债合计 / 资产总计`
- 流动比率 = `流动资产合计 / 流动负债合计`
- 速动比率 = `(流动资产合计 − 存货 − 预付账款 − 一年内到期的非流动资产) / 流动负债合计`
  (state the 速动资产 口径 you used)
- 毛利率 = `(营业收入 − 营业成本) / 营业收入`
- 净利率 = `净利润 / 营业收入`
- 净资产收益率 ROE = `净利润 / 平均所有者权益`,平均 = `(期初 + 期末) / 2`
- 总资产报酬率 ROA = `净利润 / 平均资产总计`
- 应收账款周转率 = `营业收入 / 平均应收账款`;周转天数 = `365 / 周转率`
- 存货周转率 = `营业成本 / 平均存货`
- 总资产周转率 = `营业收入 / 平均资产总计`
- 盈利质量 = `经营活动现金流量净额 / 净利润`
- 利息保障倍数 = `(利润总额 + 利息费用) / 利息费用`

A single-period ratio says little; a ratio using period-end where an average is
required overstates turnover. Use averages where the formula calls for one.

## 同比 / 环比

State the base explicitly for every change: **同比** compares with the same period
last year; **环比** compares with the immediately preceding period. `变动 = 本期 −
基期`; `变动率 = 变动 / 基期`. Guard a zero base (report absolute, mark 新增, not an
infinite ratio). Never mix units, 币种, or 准则 across a comparison.

## 税会差异 caveats

Book figures are not the tax base. Do not infer 应纳税所得额, 应交所得税, or a tax
position from book profit alone. Note that items such as 折旧年限差异,
业务招待费/广告费 限额, 资产减值准备 (not deductible until realized), 政府补助,
公允价值变动, and 递延所得税 create book–tax differences resolved at 汇算清缴. Say
what would need to be checked; do not compute a tax number from the statements.

## Output contract

`outputs/normalized/ratios.csv`:
`period, metric, formula, 分子取数, 分母取数, value, base_period, 比较类型(同比/环比),
变动, 变动率`

`outputs/exceptions/statement_ties.csv`:
`relation, statement_a, value_a, statement_b, value_b, 差异, status(tied/break), detail`

The `outputs/markdown/` report gives: the basis; the tie results (breaks first);
the ratios with their movement and named drivers; and the data-quality issues and
open questions, including 税会差异 to verify.

## Rules

- If `SCENARIO.md` names a Word template, fill that file. Do not invent a parallel markdown report.
- State period, unit, 币种, and 准则 before any number.
- Every ratio names its formula and its exact 取数科目.
- Never mix units or periods in one comparison; name the base for every change.
- Report a 勾稽 break; do not work around it. Flag a profit unsupported by
  operating cash flow.
- Report a restatement or 会计政策变更 as a caveat.
- Keep tax out of the book analysis; hand tax questions to `tax-compliance` and
  period-close ties to `tax-closing-checklist`.
