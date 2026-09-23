/**
 * API client for the env vars / secrets feature.
 *
 * Always routes through the frontend BFF (``/api/build/...``), per CLAUDE.md.
 * Reads go through `useSWR(SWR_KEYS.*, errorHandlingFetcher)`; only the
 * mutations live here. Each function throws on non-2xx with a human-readable
 * message lifted from the JSON ``detail`` field when present.
 */

import type {
  EnvVarCreateBody,
  EnvVarItem,
  EnvVarPatchBody,
} from "@/app/craft/v1/env-vars/interfaces";
import { BUILD_API_BASE } from "@/app/craft/v1/constants";

const API_BASE = `${BUILD_API_BASE}/env-vars`;

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

export async function createEnvVar(
  body: EnvVarCreateBody
): Promise<EnvVarItem> {
  const res = await fetch(API_BASE, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) await readError(res, "Failed to create env var");
  return (await res.json()) as EnvVarItem;
}

export async function updateEnvVar(
  envVarId: string,
  body: EnvVarPatchBody
): Promise<EnvVarItem> {
  const res = await fetch(`${API_BASE}/${envVarId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) await readError(res, "Failed to update env var");
  return (await res.json()) as EnvVarItem;
}

export async function deleteEnvVar(envVarId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/${envVarId}`, { method: "DELETE" });
  if (!res.ok && res.status !== 204) {
    await readError(res, "Failed to delete env var");
  }
}
