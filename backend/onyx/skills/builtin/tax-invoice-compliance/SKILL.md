---
name: tax-invoice-compliance
description: Scan invoices for required fields, tax IDs, rates, and header mismatches. Use for 发票合规 or invoice exception lists.
---

# tax-invoice-compliance

Build an exception list. Follow `document-ingest`. Digital invoices use code first.

## Checks

- Required fields present
- Buyer/seller tax ID format
- Rate vs amount
- Header / stamp mismatches (vision only)

Write `outputs/exceptions/invoice_compliance.csv`. One row per issue.
Do not stop the job because one file failed.
