/**
 * API client for the Craft Loops feature. Always routes through the
 * frontend BFF (`/api/build/...`). Each function throws on non-2xx with the
 * backend `detail` message when present.
 */

import { BUILD_API_BASE } from "@/app/craft/v1/constants";
import type {
  LoopGrant,
  LoopItem,
  LoopListItem,
  LoopOutput,
  LoopState,
  OutputDecision,
} from "@/app/craft/v1/loops/interfaces";

const API_BASE = `${BUILD_API_BASE}/loops`;

async function readError(res: Response, fallback: string): Promise<never> {
  let detail: string | undefined;
  try {
    const body = (await res.json()) as { detail?: string };
    detail = body?.detail;
  } catch {
    // ignore parse errors
  }
  throw new Error(detail || `${fallback} (HTTP ${res.status})`);
}

async function mutate<T>(
  path: string,
  method: "POST" | "PATCH" | "DELETE",
  body?: unknown,
  fallback = "Request failed"
): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) await readError(res, fallback);
  return (await res.json()) as T;
}

export async function updateLoopState(
  loopId: string,
  state: LoopState
): Promise<LoopListItem> {
  return mutate<LoopListItem>(
    `${API_BASE}/${loopId}`,
    "PATCH",
    { state },
    "Failed to update loop"
  );
}

export async function deleteLoop(loopId: string): Promise<{ success: boolean }> {
  return mutate<{ success: boolean }>(
    `${API_BASE}/${loopId}`,
    "DELETE",
    undefined,
    "Failed to delete loop"
  );
}

export async function retryLoopItem(
  loopId: string,
  itemId: string
): Promise<LoopItem> {
  return mutate<LoopItem>(
    `${API_BASE}/${loopId}/items/${itemId}/retry`,
    "POST",
    undefined,
    "Failed to retry item"
  );
}

export async function decideLoopOutput(
  loopId: string,
  outputId: string,
  decision: OutputDecision,
  note?: string
): Promise<LoopOutput> {
  return mutate<LoopOutput>(
    `${API_BASE}/${loopId}/outputs/${outputId}/decision`,
    "POST",
    { decision, note: note ?? null },
    "Failed to decide output"
  );
}

export async function createLoopGrant(
  loopId: string,
  shipAction: string,
  label: string | null
): Promise<LoopGrant> {
  return mutate<LoopGrant>(
    `${API_BASE}/${loopId}/grants`,
    "POST",
    { ship_action: shipAction, label },
    "Failed to create grant"
  );
}

export async function setLoopAutopilot(
  loopId: string,
  enabled: boolean
): Promise<LoopListItem> {
  return mutate<LoopListItem>(
    `${API_BASE}/${loopId}/autopilot`,
    "POST",
    { enabled },
    "Failed to set autopilot"
  );
}

/** Seed ledger items directly. Used by tests and power users. */
export async function intakeLoopItems(
  loopId: string,
  items: { source_key: string; source_summary?: string }[]
): Promise<{ created: number; items: LoopItem[] }> {
  return mutate<{ created: number; items: LoopItem[] }>(
    `${API_BASE}/${loopId}/items`,
    "POST",
    { items },
    "Failed to add items"
  );
}
