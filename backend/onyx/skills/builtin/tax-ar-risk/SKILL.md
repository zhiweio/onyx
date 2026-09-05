---
name: tax-ar-risk
description: Rank high-risk 应收账款 customers by combining 账龄分桶, 逾期天数, 周转率/周转天数, 集中度, 回款趋势, and external credit signals from an optional credit MCP (启信宝/企查查/天眼查), then write a scored risk table with cited external flags. Use for 应收高风险, 应收账款风险, 账龄分析, AR risk, receivable risk, or customer credit risk.
---

# tax-ar-risk

Score and rank receivable customers by collection risk. Follow `long-job-protocol`
and `document-ingest`. When a credit MCP is configured, save every raw body under
`outputs/mcp/<server>/<call>.json` and cite that file for each external claim.
Never invent a 被执行 record, a 案号, or a rating.

## Inputs contract

Required (at least one):
- An AR aging table (应收账款账龄表) per customer, or
- AR detail (应收明细) with 开票日期, 金额, 客户, and 账期/到期日 so aging can be
  built.

Strongly preferred:
- 营业收入 for the period (for 周转率 / DSO).
- 收款 / 回款记录 (for the collection trend).
- The 信用政策 / 账期 per customer (to compute 逾期, not just 账龄).
- The existing 坏账准备 policy (组合 rates by 账龄, and any 单项 items).

Optional:
- A credit MCP (e.g. 启信宝, 企查查, 天眼查) for external signals.

If aging cannot be built and no aging table exists, stop and ask. If no credit MCP
is configured, say external signals are unavailable and rank on internal data
only — do not fabricate them.

## Phases

1. **plan** — Write `outputs/plan/PLAN.md`: the AR source, whether 收入/回款/账期
   are available, the aging buckets, and whether a credit MCP is configured. Done
   when the scoring inputs are enumerated.
2. **ingest** — Run `document-ingest` on the AR and collection files. Done when
   every file has a MANIFEST row.
3. **normalize** — Write `outputs/normalized/ar_detail.csv` and, per customer, the
   bucketed balances. Done when Σ customer balances equals the AR control total.
4. **enrich** — If a credit MCP exists, query per customer, save raw bodies under
   `outputs/mcp/`, and keep only a digest inline. Done when every queried customer
   has an MCP file or an explicit "no record".
5. **score** — Compute the risk score and write `outputs/normalized/ar_risk.csv`.
   Done when every customer has a score and a reason.
6. **compose / review** — Rank, write to `outputs/markdown/`, and re-check the top
   names against their MCP files. Done when each top-risk reason is cited.

## Aging and turnover

- **账龄分桶** — bucket each customer's balance into
  `0–30 / 31–60 / 61–90 / 91–180 / 181–365 / >365` 天, measured from 开票日 (or the
  aging table's own basis; state which). Keep the oldest-bucket amount visible — it
  drives risk more than the total.
- **逾期天数** — `报告日 − 到期日`, where `到期日 = 开票日 + 账期`. 账龄 counts from
  the invoice; 逾期 counts from the due date. Report both; do not conflate them.
- **周转率与周转天数** — `应收账款周转率 = 营业收入 / 平均应收账款`, where
  `平均应收账款 = (期初 + 期末) / 2`; `周转天数 = 365 / 周转率`. Or per-customer
  `DSO = 期末应收 / 营业收入 × 天数`. Name the denominator every time.

## 坏账准备 interaction

Read, do not re-decide, the client's policy. Under 预期信用损失 (ECL):
- **组合计提** — apply the 账龄-based loss rates to the bucketed balances; older
  buckets carry higher rates.
- **单项计提** — specific customers assessed individually (disputed, insolvent,
  litigated). Keep 单项 customers out of the 组合 pool so they are not
  double-counted.
Report the implied provision per customer, but flag that the booked provision is
the client's judgement — you are surfacing risk, not restating the accounts.

## External signals and weighting

When the credit MCP returns data, weight signals by source authority, highest
first, and cite the `outputs/mcp/...json` file for each:

1. 失信被执行人 / 被执行人 / 限制高消费 (official enforcement) — strongest.
2. 严重违法失信 / 经营异常名录.
3. 股权冻结 / 大量涉诉 / 立案.
4. 欠税公告.
5. 评级下调 / 舆情 (commercial or news) — weakest; corroborate before weighting.

Official enforcement outranks commercial ratings, which outrank news. A single
news snippet is a lead, not a fact.

## Scoring and output

Combine internal severity (oldest 账龄, 逾期天数, worsening 回款趋势, 集中度 =
customer share of total AR) with the external weight into `risk_level`
(high / medium / low), and always record the human-readable `risk_reason`.

`outputs/normalized/ar_risk.csv`:
`客户名称, 客户税号, 应收余额, bkt_0_30, bkt_31_60, bkt_61_90, bkt_91_180,
bkt_181_365, bkt_over_365, 最长账龄天数, 逾期天数, DSO, 回款趋势(升/平/降),
占比, 计提方式(单项/组合), 估算坏账准备, external_flags, external_source_ref,
risk_score, risk_level, risk_reason`

The `outputs/markdown/` report leads with the ranked high-risk customers, each
with its numeric drivers and cited external flags, then the concentration picture
(top-N share of AR), then customers with no external data marked as such.

## Rules

- If `SCENARIO.md` names a Word template, fill that file. Do not invent a parallel markdown report.
- Every external claim cites its `outputs/mcp/...json` file. No file, no claim.
- Distinguish 账龄 from 逾期; a long 账龄 within account terms is not yet overdue.
- Name the denominator for 周转率 / DSO and the base for any trend.
- Do not restate the client's 坏账准备; surface risk and let them decide.
- If external data is unavailable, say so and rank on internal signals only.
