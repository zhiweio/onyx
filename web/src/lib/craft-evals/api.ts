import { parseErrorDetail } from "@/lib/fetcher";
import { extractContentFromMetadata } from "@/app/craft/services/apiServices";
import type {
  CraftEvalCaseSummary,
  CraftEvalRunDetail,
  CraftEvalRunSummary,
} from "@/lib/craft-evals/types";

const BASE = "/api/build/admin/evals";

async function readJson<T>(response: Response, fallback: string): Promise<T> {
  if (!response.ok) {
    throw new Error(await parseErrorDetail(response, fallback));
  }
  // SAFETY: every caller pairs a route with the response model that route
  // is typed to return in the backend, so the parsed body matches T.
  return response.json() as Promise<T>;
}

export async function listCraftEvalCases(): Promise<CraftEvalCaseSummary[]> {
  return readJson<CraftEvalCaseSummary[]>(
    await fetch(`${BASE}/cases`),
    "Could not load eval cases"
  );
}

export async function listCraftEvalRuns(
  limit: number
): Promise<CraftEvalRunSummary[]> {
  return readJson<CraftEvalRunSummary[]>(
    await fetch(`${BASE}/runs?limit=${encodeURIComponent(limit)}`),
    "Could not load eval runs"
  );
}

export async function getCraftEvalRun(
  runId: string
): Promise<CraftEvalRunDetail> {
  return readJson<CraftEvalRunDetail>(
    await fetch(`${BASE}/runs/${encodeURIComponent(runId)}`),
    "Could not load eval run"
  );
}

export async function triggerCraftEvalRun(
  caseSlugs: string[] | null
): Promise<CraftEvalRunDetail> {
  return readJson<CraftEvalRunDetail>(
    await fetch(`${BASE}/runs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ case_slugs: caseSlugs }),
    }),
    "Could not trigger eval run"
  );
}

// ---------------------------------------------------------------------------
// Eval session transcript
// ---------------------------------------------------------------------------

/** One readable entry of an eval session transcript. */
export interface EvalTranscriptEntry {
  id: string;
  role: "user" | "assistant" | "tool";
  content: string;
  /** Human label for tool entries; null for user/assistant entries. */
  toolLabel: string | null;
  turnIndex: number;
  createdAt: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function parseTranscriptMessage(message: unknown): EvalTranscriptEntry | null {
  if (!isRecord(message)) {
    return null;
  }
  const type = typeof message.type === "string" ? message.type : "";
  const role =
    type === "user" ? "user" : type === "assistant" ? "assistant" : "tool";
  const metadata = isRecord(message.message_metadata)
    ? message.message_metadata
    : null;
  const toolLabelValue =
    metadata?.title ?? metadata?.name ?? metadata?.tool_name;
  return {
    id: typeof message.id === "string" ? message.id : "",
    role,
    content: extractContentFromMetadata(metadata),
    toolLabel:
      role === "tool" && typeof toolLabelValue === "string" && toolLabelValue
        ? toolLabelValue
        : null,
    turnIndex: typeof message.turn_index === "number" ? message.turn_index : 0,
    createdAt: typeof message.created_at === "string" ? message.created_at : "",
  };
}

/**
 * Read-only transcript of an EVAL-origin session, via the admin evals API.
 * The regular per-user session endpoints 404 for admins because eval
 * sessions belong to the eval service account.
 */
export async function listEvalSessionTranscript(
  sessionId: string
): Promise<EvalTranscriptEntry[]> {
  const res = await fetch(
    `${BASE}/sessions/${encodeURIComponent(sessionId)}/messages`
  );
  if (!res.ok) {
    throw new Error(
      await parseErrorDetail(res, "Could not load session transcript")
    );
  }
  const payload: unknown = await res.json();
  if (!isRecord(payload) || !Array.isArray(payload.messages)) {
    throw new Error("Could not load session transcript");
  }
  return payload.messages.flatMap((message) => {
    const entry = parseTranscriptMessage(message);
    return entry ? [entry] : [];
  });
}
