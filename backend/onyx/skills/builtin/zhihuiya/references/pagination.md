# Pagination

Know the layer before you call:

| Layer | Rule |
| --- | --- |
| 检索 / 线索 | One page. `limit=100` or `top_k=100`. |
| 计数 | Read `total`, or aggregate pages you already fetched. |
| 明细 | Page to the end. Write the 检索深度对账表 before the report. |

Caps:

- `patsnap_search`: `offset + limit ≤ 1000`
- landscape / monetize: `≤ 20000`

Write `outputs/mcp/zhihuiya/stores/<report-id>/digest/pagination.md` with
requested, returned, `total`, and whether the walk finished.
