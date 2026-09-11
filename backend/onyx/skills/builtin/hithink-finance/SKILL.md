---
name: hithink-finance
description: Query Tonghuashun HiThink listed-company quotes, filings, funds, futures, and options. Use for A-share, 同花顺, 行情, 财报, 基金, 期货, or options.
required-mcp:
  - hithink-a-share
  - hithink-a-share-index
  - hithink-meta
  - hithink-fund
  - hithink-futures
  - hithink-options
---

# hithink-finance

Use HiThink MCP for live China-market facts. Do not invent a ticker, 证券代码,
or filing date.

The sandbox image already has `@hithink-tech/hithink-finance-cli`. Prefer the
gateway MCP tools. Do not ask the user to paste an API key.

## Phases

1. **resolve** — Call `hithink-meta` and write `outputs/entity.json` with the
   official name, 证券代码, and exchange. Stop if the entity is ambiguous.
2. **fetch** — Use `hithink-a-share` for filings and financials,
   `hithink-a-share-index` for industry peers, and the fund / futures / options
   servers only when the question needs them.
3. **cite** — Every figure names the tool, period, and 币种. Save raw bodies
   under `outputs/mcp/hithink/`.

## Rules

- Quotes are intra-day. State the as-of time.
- If a server is not authenticated, say so and continue with the others.
- Do not enable unused HiThink servers for a simple name lookup.
