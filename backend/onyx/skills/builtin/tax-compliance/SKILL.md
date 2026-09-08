---
name: tax-compliance
description: Produce a cited China tax compliance risk brief for a named company from official registries, judicial sites, and configured commercial MCP sources, ranking risk and refusing to invent 文号 or 案号. Use for 税务合规, 合规, 稽查, 违法, 风险预警, 涉税风险, tax compliance risk, VAT/CIT exposure, or credit checks.
---

# tax-compliance

Produce a cited China tax compliance risk brief.
Prefer live sources over memory. Save raw MCP bodies under
`outputs/mcp/<server>/<call>.json` and keep only a digest inline. Never invent a
文号, 案号, 处罚决定书, penalty amount, or policy document — a citation you cannot
retrieve does not exist.

## Inputs contract

Required:
- The company's legal name and 统一社会信用代码 (18 位). A name alone is ambiguous;
  confirm the 税号 before attributing any record to the company.

Optional, sharpens scope:
- 纳税人识别号 (if different), trading names, and 关联方 names.
- The risk scope (发票 / 申报 / 稽查 / 信用 / 司法 / 关联交易) and the period.

If no 统一社会信用代码 is given and the name maps to several entities, stop and ask
which one. Do not guess.

## Source hierarchy (highest authority first)

1. **国家税务总局 and 各级税务局** — official announcements, 税务行政处罚决定书
   公示, 重大税收违法失信主体 公告.
2. **信用中国 (creditchina.gov.cn)** and **国家企业信用信息公示系统 (gsxt.gov.cn)** —
   official registry: 经营异常, 严重违法失信, 行政处罚.
3. **中国裁判文书网** and **中国执行信息公开网** — official judicial: 涉税诉讼,
   被执行人, 失信被执行人, 限制高消费.
4. **商业数据库 MCP** (启信宝 / 企查查 / 天眼查) — supporting aggregation only, not
   an official filing.
5. **新闻 / 自媒体** — a lead to verify against the sources above, never a fact on
   its own.

When a lower source and a higher source disagree, the higher one wins. A
commercial MCP result is corroboration, not an STA filing.

## Phases

1. **plan** — Write `outputs/PLAN.md`: the entity + 税号, the scope, and which
   MCP servers are configured. Done when the entity is unambiguous and the source
   set is listed.
2. **gather** — Query official registries/judicial sites (browser or web search)
   and, where configured, the commercial MCP; write notes with citations to
   `outputs/research/<role>/*.md` and raw MCP bodies to `outputs/mcp/`. Done when
   each risk dimension has been searched (with a hit or an explicit "no record").
3. **assess** — Rate each finding and the overall risk; write
   `outputs/normalized/findings.csv`. Done when every finding carries a source and a
   severity.
4. **compose** — Write the brief to `outputs/markdown/`. Done when every material
   claim in the brief cites a retrieved source.
5. **review** — Re-open the top findings against their cited source. Done when each
   is confirmed or downgraded.

## Risk dimensions to search

- **发票风险** — 虚开, 异常凭证, 失控发票, 走逃(失联)企业.
- **申报与欠税** — 欠税公告, 未按期申报, 滞纳金.
- **稽查与处罚** — 税务行政处罚决定书, 稽查案件.
- **纳税信用等级** — A/B/M/C/D 级; a D 级 rating carries real downstream
  consequences — note them if the rating is retrieved.
- **涉税司法** — 涉税诉讼, 涉税刑事, 被执行/失信被执行人.
- **经营与主体状态** — 经营异常名录, 严重违法失信, 注销/吊销.
- **优惠资格与关联交易** — 高新 / 小微 / 加计扣除 资格 risk, 关联交易 / 转让定价
  exposure — describe the risk, do not compute a tax number.

## Citation requirements

Every material claim carries the fields for its type; a claim missing them is not
usable:

- Policy / 公告 / 处罚: **发文/处罚机关, 文号, 发文日期, 生效日期, URL, 检索日期**.
- Court case: **案号, 审理法院, 裁判日期, URL**.
- Registry record: **来源系统, 记录日期, URL, 检索日期**.

Do not synthesize a 文号 or 案号 that "looks right". If you cannot retrieve the
identifier, say the record is unverified.

## Output contract

`outputs/normalized/findings.csv`:
`dimension, finding, severity(high/medium/low), source_type(official/judicial/commercial/news),
文号或案号, 发文或裁判机关, 日期, url, mcp_ref, 检索日期`

The `outputs/markdown/` brief has: the entity and 税号; the findings grouped by
dimension, each with its citation; the overall risk level (high / medium / low)
with the reasons; open questions; and recommended next checks. State which sources
were unavailable.

## Rules

- If `SCENARIO.md` names a Word template, fill that file. Do not invent a parallel markdown report.
- Cite every material claim with a URL and a date when present.
- Commercial MCP results are supporting only; do not present them as official STA
  filings.
- Never invent 文号, 案号, penalties, or policy documents.
- If a tool or source returns empty, report that source as unavailable — do not
  fill the gap from memory.
- For the underlying policy behind a finding, hand off to `tax-policy-trend`; for
  book figures, to `tax-financial-statement`.
