export interface CraftEvalCaseSummary {
  slug: string;
  name: string;
  domain: string;
  scenario_slug: string | null;
  skill_slugs: string[];
  report_contract_slug: string | null;
  budget_seconds: number;
  expected_paths: string[];
  rubric_criterion_count: number;
  value_anchor_count: number;
}

/** Shape of the deterministic-findings JSONB on a case result. */
export interface EvalFindingsBlob {
  findings?: unknown;
  passed?: unknown;
  total?: unknown;
}

/** Shape of the judge-verdict JSONB on a case result. */
export interface EvalJudgeBlob {
  checks?: unknown;
  error?: unknown;
  comment?: unknown;
  model?: unknown;
  omitted?: unknown;
}

/** Shape of the run-summary JSONB (regression diff etc.). */
export interface EvalRunSummaryBlob {
  case_scores?: unknown;
  case_statuses?: unknown;
  pass_threshold?: unknown;
  regressions?: unknown;
  previous_run_id?: unknown;
  previous_score?: unknown;
}

export interface CraftEvalCaseResult {
  case_slug: string;
  case_name: string;
  domain: string;
  status: string;
  score: number | null;
  duration_seconds: number | null;
  session_id: string | null;
  error_detail: string | null;
  deterministic_findings: EvalFindingsBlob;
  judge_verdict: EvalJudgeBlob;
}

export interface CraftEvalRunSummary {
  id: string;
  trigger: string;
  status: string;
  case_count: number;
  passed_count: number;
  score: number | null;
  model_provider: string | null;
  model_name: string | null;
  error_detail: string | null;
  created_at: string;
  finished_at: string | null;
}

export interface CraftEvalRunDetail extends CraftEvalRunSummary {
  summary: EvalRunSummaryBlob;
  case_results: CraftEvalCaseResult[];
}

export interface EvalDeterministicFinding {
  check: string;
  passed: boolean;
  detail: string;
  weight?: number;
}

export interface EvalJudgeCheck {
  id: string;
  verdict: string;
  evidence: string;
  confidence?: string;
}

/** Strict-shape readers for the JSONB blobs on case results. */

function hasFields<T extends object>(
  item: unknown,
  keys: (keyof T & string)[]
): item is Partial<T> {
  return (
    typeof item === "object" &&
    item !== null &&
    keys.every((key) => key in item)
  );
}

export function readFindings(value: EvalFindingsBlob): EvalDeterministicFinding[] {
  if (!Array.isArray(value.findings)) {
    return [];
  }
  const out: EvalDeterministicFinding[] = [];
  for (const item of value.findings) {
    if (!hasFields<EvalDeterministicFinding>(item, ["check", "passed"])) {
      continue;
    }
    const { check, passed } = item;
    if (typeof check === "string" && typeof passed === "boolean") {
      out.push({
        check,
        passed,
        detail: typeof item.detail === "string" ? item.detail : "",
      });
    }
  }
  return out;
}

export function readJudgeChecks(value: EvalJudgeBlob): EvalJudgeCheck[] {
  if (!Array.isArray(value.checks)) {
    return [];
  }
  const out: EvalJudgeCheck[] = [];
  for (const item of value.checks) {
    if (!hasFields<EvalJudgeCheck>(item, ["id", "verdict"])) {
      continue;
    }
    const { id, verdict } = item;
    if (typeof id === "string" && typeof verdict === "string") {
      out.push({
        id,
        verdict,
        evidence: typeof item.evidence === "string" ? item.evidence : "",
        confidence:
          typeof item.confidence === "string" ? item.confidence : undefined,
      });
    }
  }
  return out;
}

interface RegressionEntry {
  case: string;
  previous_score: number;
  score: number;
}

export function readRegressions(summary: EvalRunSummaryBlob): RegressionEntry[] {
  if (!Array.isArray(summary.regressions)) {
    return [];
  }
  const out: RegressionEntry[] = [];
  for (const item of summary.regressions) {
    if (!hasFields<RegressionEntry>(item, ["case"])) {
      continue;
    }
    if (typeof item.case === "string") {
      out.push({
        case: item.case,
        previous_score: Number(item.previous_score ?? 0),
        score: Number(item.score ?? 0),
      });
    }
  }
  return out;
}

export const NON_TERMINAL_RUN_STATUSES = new Set(["queued", "running"]);

export function isRunTerminal(status: string): boolean {
  return !NON_TERMINAL_RUN_STATUSES.has(status);
}
