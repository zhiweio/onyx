# Official Qichacha MCP

Call official Qichacha MCP tools. The Onyx gateway already proxies
`https://agent.qcc.com/mcp/{server}/stream` (see https://agent.qcc.com/guide).
Official MCP already dehydrates long lists and returns a decision summary.
The gateway caches the full body. Treat the MCP result as the source of
truth.

Do not run `qcc`, `qcc-agent-cli`, `npx qcc-document-mcp`, or any other
Qichacha CLI. Do not install a CLI. Do not ask the user for an API key.

## Servers

| Need | Server |
| --- | --- |
| Entity, registry, shareholders, UBO, finance | qcc-company |
| Risk, litigation, execution, tax, bankruptcy | qcc-risk |
| Patents, trademarks, copyrights | qcc-ipr |
| Bidding, licenses, news, recruitment | qcc-operation |
| Historical snapshots (needs enterprise cert) | qcc-history |
| Person risk (name + company) | qcc-executive |
| Regulation search | qcc-legal-regulation |
| Similar-case search | qcc-legal-case |
| Open tenders | qcc-tender |
| Public document URL parse | qcc-document |

Call the tool by its official name on that server, for example
`get_company_registration_info` on `qcc-company`. The gateway may prefix
the LLM name. Match on the official tool name.

If a listed MCP resource such as `qcc://policy/entity-anchoring` is
available, read it once in the session. Skip it when the client has no
resources.

## Anchor

1. If the input is a short name, brand, or ticker, call
   `get_company_by_query` on `qcc-company`.
2. Stop when more than one candidate remains. Do not pick a near match.
3. Lock the 登记名 and 18-digit 统一社会信用代码.
4. Call `verify_company_accuracy` when the user also gave a credit code.

`qcc-executive` tools need both the company key and the person name.

## Scan then drill

When the task covers two or more risk dimensions:

1. Call `get_company_risk_scan` on `qcc-risk` after the entity is locked.
2. Drill only dimensions with count > 0.
3. Count = 0 means no record. Do not call that atom tool.
4. A single-dimension question may skip the scan.
5. Do not give a qualitative label until the drill tool returned rows.
   Write `N 条（未取明细）` when you skip the drill.

For a person, call `get_executive_risk_scan` first. For related parties,
call `get_company_related_risk_scan` or `get_executive_related_risk_scan`
once. Do not scan every related company.

Leave `year` empty to take the full set. Do not loop year by year.

## Cite

Quote ratios and case numbers as the tool returned them. Do not multiply
share layers. Do not invent a 案号 or 统一社会信用代码. Write
`outputs/mcp/qichacha/` for raw bodies. In the customer report, use
business language only.
