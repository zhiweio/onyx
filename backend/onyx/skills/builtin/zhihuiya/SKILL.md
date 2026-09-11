---
name: zhihuiya
description: Route Zhihuiya / Patsnap patent, biomed, and company-diligence work. A /zhihuiya pick enables the starter set only. Use for 智慧芽, 专利, FTO, 管线, or company credit.
mcp-groups:
  zhihuiya-starter:
    - pharma-intelligence
    - patsnap-search
    - biology-modality
    - patent-analysis
    - patent-briefing
    - company-credit
  zhihuiya-patent:
    - patsnap-search
    - patent-briefing
    - patsnap-analytics
    - patent-landscape
    - patent-analysis
    - patent-value
    - patent-status
  zhihuiya-biomed:
    - pharma-intelligence
    - target-disease
    - biology-modality
    - literature-search
    - drug-asset
    - chemical-molecular
  zhihuiya-company:
    - company-credit
    - company-profile
    - company-risk
    - tech-diligence
    - company-tags
default-mcp-group: zhihuiya-starter
---

# zhihuiya

Route work. Do not load every Zhihuiya server. `/zhihuiya` enables the starter
group only. Pick extra servers in `/` when the starter set is not enough.

Read `references/tool-map.md`, `references/pitfalls.md`, and
`references/pagination.md` before the first tool call.

## Evidence

Large MCP results are not evidence. Write every capture through
`scripts/replay_store.py` under `outputs/mcp/zhihuiya/stores/<report-id>/`.
If a body is tagged `TRUNCATED-SEED`, refetch before you cite it.

## Defaults

- Search: `patsnap-search` with `limit=100`. `offset + limit` must stay ≤ 1000.
- Detail: `patent-briefing`. Kind code is required on `pn`.
- News: `ls_web_search`, not `news_search`.
- Count layer: read `total` or aggregate. Do not guess.
- Clue layer: one page.
- Detail layer: page to the end, then write the 检索深度对账表.

## Refusal

Do not invent a publication number, family id, or sequence identity. Sequence
identity is an integer percent from a tool, not an estimate.
