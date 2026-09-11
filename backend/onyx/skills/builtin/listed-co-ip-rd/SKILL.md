---
name: listed-co-ip-rd
description: Map a listed company's patents and R&D using Zhihuiya. Must use replay_store and a pagination audit table. Use for 专利, 研发, or IP diligence.
mcp-groups:
  zhihuiya-ip-rd:
    - patsnap-search
    - patent-briefing
    - patsnap-analytics
    - patent-landscape
    - company-credit
    - company-profile
    - company-risk
    - tech-diligence
default-mcp-group: zhihuiya-ip-rd
---

# listed-co-ip-rd

Follow the `zhihuiya` skill. Write every capture through
`zhihuiya/scripts/replay_store.py`. Write the 检索深度对账表 before the
narrative.

Do not cite `mcp-offload` dumps. Refetch `TRUNCATED-SEED` bodies.
