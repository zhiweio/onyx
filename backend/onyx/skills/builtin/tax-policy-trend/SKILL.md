---
name: tax-policy-trend
description: Research China tax policy trends for a tax type, region, and industry, and write a cited outlook that separates enacted rules from commentary and states each document's effective status. Use for 税收政策, 政策, 趋势, 公告, 税率变化, 税收优惠, tax policy trend, or industry tax planning.
---

# tax-policy-trend

Produce a cited China tax policy trend note from documents you actually
retrieved. Save raw MCP bodies under
`outputs/mcp/<server>/<call>.json`. Quote 文号 and 发文机关 from fetched records
only. Do not invent a notice, and do not assert a rule's current effective status
without retrieving it.

## Inputs contract

Required:
- The tax type: 增值税 (VAT), 企业所得税 (CIT), 个人所得税 (IIT), 关税, 消费税,
  印花税, 房产税, 城镇土地使用税, 环境保护税, 资源税, or 社保费.

Optional, narrows the scan:
- Region (国家级 vs 省/市 地方口径) and industry.
- The time window of interest and the decision the note will feed.

If the tax type is unstated, ask; a trend note across all taxes is too broad to be
useful. If R&D incentives (研发费用加计扣除) or IP-linked reliefs matter and a
Patsnap-style MCP is configured, query it too.

## Source hierarchy (legal force, highest first)

1. **全国人大及其常委会** — 税收法律 (e.g. 企业所得税法, 个人所得税法).
2. **国务院** — 行政法规 / 实施条例, 国发 / 国办发.
3. **财政部 + 国家税务总局** — joint 财税〔〕号 and 财政部 税务总局公告〔〕号.
4. **国家税务总局** — 公告 / 税总函.
5. **省 / 市 财政 与 税务局** — 地方规范性文件 and 口径.
6. **12366 纳税服务 / 官方解读** — interpretation, not the rule itself.
7. **商业数据库 MCP** — aggregation and cross-reference.
8. **新闻 / 自媒体** — a lead to verify, never an enacted rule.

## Phases

1. **plan** — Write `outputs/PLAN.md`: the tax type, region, industry, window,
   and configured sources. Done when scope and sources are fixed.
2. **gather** — Search official sources first, then commercial, then news; write
   notes with citations to `outputs/research/<role>/*.md` and raw MCP bodies to
   `outputs/mcp/`. Done when the enacting documents are located or reported
   unavailable.
3. **assess** — For each document, record what changed, who is affected, the
   effective status, and the dates; write `outputs/normalized/policy_timeline.csv`.
   Done when every entry has a verified status.
4. **compose** — Write the trend note to `outputs/markdown/`. Done when every
   claim cites a retrieved document.
5. **review** — Re-check effective status and 文号 against the source. Done when no
   claim rests on a news snippet.

## Effective status (verify, never assume)

For every document, record its status: **现行有效 / 部分失效 / 全文失效 / 尚未施行**.
Many Chinese tax reliefs are time-limited (有效期) and then continued by a later
公告 — for example 小微企业 relief and 研发费用加计扣除 have been extended more than
once. Do not state that a policy is "still in effect" or quote a rate as current
unless you retrieved the governing document and its 有效期. Where a well-known rate
band exists (e.g. VAT 13% / 9% / 6%), treat it as something to confirm against the
current 税率表, not as an asserted fact.

## Citation requirements

Each policy claim carries: **文号, 发文机关, 发文日期, 施行/生效日期, 有效期, URL,
检索日期**. Separate the enacting document from any 解读 or news that describes it,
and label which is which. A trend built on commentary alone is not a policy note.

## Output contract

`outputs/normalized/policy_timeline.csv`:
`tax_type, 文号, 发文机关, 发文日期, 生效日期, 有效期, 状态(现行有效/部分失效/全文失效/尚未施行),
主题, 影响主体, source_type(law/regulation/announcement/local/interpretation/commercial/news),
url, 检索日期`

The `outputs/markdown/` note has: what changed (enacted documents, quoted 文号);
who is affected; effective dates and status; open implementation questions
(待落地口径); and sources, official separated from commentary. State which sources
were unavailable.

## Rules

- If `SCENARIO.md` names a Word template, fill that file. Do not invent a parallel markdown report.
- Quote 文号 and 发文机关 from fetched records; never fabricate a notice.
- Separate official policy from news commentary; a news snippet is not an enacted
  rule.
- Do not assert current effective status or a current rate without retrieving the
  governing document.
- Report an unavailable source as unavailable.
- For a specific company's exposure to a change, hand off to `tax-compliance`.
