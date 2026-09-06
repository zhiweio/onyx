---
name: data-analysis
description: Analyze tabular data and report findings with the numbers and method that support them. Covers profiling, data-quality checks, aggregation, period comparison, cohorts, and outliers. Use for 数据分析, 报表分析, 同比, 环比, 透视, 异常值, trend analysis, cohort, pivot, or outlier detection.
---

# data-analysis

Analyze a table and report what the numbers actually show. Follow
`long-job-protocol` for anything that spans more than one turn.

## Scope

Answers: what does this data say about a stated question, how confident can we
be, and what is wrong with the data itself.

Does not cover: reading the files (use `document-ingest` and `xlsx`), or writing
the finished document (use `docx` / `pptx`).

## Workflow

1. **State the question** — Write the question, the metric definition, the grain
   (one row = what?), and the time window into `outputs/plan/PLAN.md`. If the ask
   is vague, pick one specific reading and record which.
   **Done when:** PLAN.md names the metric, the grain, and the window.

2. **Profile before analyzing** — Never aggregate a table you have not profiled.
   Record row count, column names and dtypes, null counts, distinct counts for
   key columns, and min/max for dates and numerics.
   **Done when:** `outputs/normalized/profile.csv` exists and the grain is
   confirmed — check that the key you believe is unique actually is.

3. **Check quality** — Run the checks below and write every failure to
   `outputs/exceptions/data_quality.csv` with the row key and the reason. Report
   them; never silently drop rows.
   **Done when:** every exception is either explained or listed as unexplained.

4. **Compute** — Aggregate with `pandas`. Keep the computation in a script under
   `outputs/`, not in chat, so a later turn can rerun it.
   **Done when:** `outputs/normalized/<metric>.csv` holds the result table.

5. **Write the finding** — Lead with the answer, then the number, then the
   method. Every percentage names its denominator; every change names its base
   period.
   **Done when:** `outputs/markdown/analysis.md` is written and every number in
   it traces to a file in `outputs/normalized/`.

## Data-quality checks

| Check | Why it matters |
| --- | --- |
| Duplicate keys on the claimed grain | Silently doubles every sum |
| Mixed units in one column (元 vs 万元, %, bps) | Numbers off by orders of magnitude |
| Mixed currencies with no FX column | Sums are meaningless |
| Blank periods in a time series | A "decline" that is really missing data |
| Type drift (numbers as text, dates as strings) | Silent coercion or dropped rows |
| Whitespace or full-width characters in join keys | Join misses that look like real gaps |
| Sign conventions (refunds, reversals, credit balances) | Nets away real volume |
| Different as-of dates across joined sources | Apparent variance that is pure timing |

## Comparison rules

- **同比 (YoY)** compares to the same period one year earlier; **环比 (MoM/QoQ)**
  compares to the immediately preceding period. State which you used — they can
  point in opposite directions.
- Percentage change from a zero or negative base is undefined or misleading.
  Report the absolute change and say why.
- When comparing periods of unequal length or unequal business days, normalize
  (per day, per business day) or state explicitly that you did not.
- Decompose a total movement into its parts (price × volume, or by segment) and
  confirm the parts reconcile to the total before attributing a cause.
- A rate on a small denominator is noise. State the denominator beside the rate
  and suppress slices below a threshold you name.

## Outliers

Identify with a stated rule — IQR fence, z-score, or a domain threshold — and
name the rule in the output. An outlier is a finding to investigate, not a row to
delete. Keep outliers in the dataset and flag them in a column unless the user
asks otherwise.

## Output contract

- `outputs/normalized/profile.csv` — column, dtype, nulls, distinct, min, max
- `outputs/normalized/<metric>.csv` — the result table, one row per group
- `outputs/exceptions/data_quality.csv` — row key, check, detail
- `outputs/markdown/analysis.md` — question, data summary, findings, limitations

## Rules

- If `SCENARIO.md` names a Word template, fill that file. Do not invent a parallel markdown report.
- Every number you state must come from a computation run in this session, not
  from memory.
- Name the denominator for every ratio and the base period for every change.
- Do not extrapolate beyond the observed range, and do not forecast unless asked
  and the method is stated.
- Report correlation as correlation. Do not describe it as cause.
- Charts only when they add information — a trend or a distribution. Three
  numbers belong in a sentence.
- If the data cannot answer the question, say so and name exactly what is
  missing.
