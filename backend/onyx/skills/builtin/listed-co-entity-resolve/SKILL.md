---
name: listed-co-entity-resolve
description: Resolve a listed company to one official name, ticker, and credit code before any audit. Use for 证券代码, 上市公司主体, or entity resolution.
optional-mcp:
  - hithink-meta
  - qcc-company
---

# listed-co-entity-resolve

Write `outputs/entity.json` before any other listed-company skill runs.

Required fields: official name, 证券代码, exchange, 统一社会信用代码 when
Qichacha is available.

If HiThink meta is configured, use it first. Confirm with `qcc-company` when
that server is authenticated. If two sources disagree, stop and name the clash.

Done when `outputs/entity.json` has one entity and no aliases left unresolved.
