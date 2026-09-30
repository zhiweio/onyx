import { errorHandlingFetcher } from "@/lib/fetcher";

export interface AgentModelOverlay {
  id: number;
  name: string;
  template_model_id: string;
  base_url: string | null;
  enabled: boolean;
  verified_at: string | null;
  verify_error: string | null;
}

export interface AgentModelView {
  model_id: string;
  provider: string;
  display_name: string;
  context_window: number;
  max_output_tokens: number;
  runtimes: string[];
  is_default: boolean;
  notes: string;
  overlay: AgentModelOverlay | null;
}

export interface AgentModelListResponse {
  models: AgentModelView[];
}

export interface OverlayCreateBody {
  name: string;
  provider: string;
  template_model_id: string;
  model_id?: string;
  base_url?: string | null;
  context_window?: number | null;
  max_output_tokens?: number | null;
}

export function fetchAgentModels(): Promise<AgentModelListResponse> {
  return errorHandlingFetcher<AgentModelListResponse>(
    "/api/admin/agent-models"
  );
}

async function mutateAgentModels(
  path: string,
  init: RequestInit
): Promise<void> {
  const resp = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json" },
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${resp.status}`);
  }
}

export function createAgentModelOverlay(
  body: OverlayCreateBody
): Promise<void> {
  return mutateAgentModels("/api/admin/agent-models", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function verifyAgentModelOverlay(overlayId: number): Promise<{
  verified_at: string | null;
  verify_error: string | null;
}> {
  return fetch(`/api/admin/agent-models/${overlayId}/verify`, {
    method: "POST",
  }).then(async (resp) => {
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      throw new Error(body.detail || `HTTP ${resp.status}`);
    }
    return resp.json();
  });
}

export function deleteAgentModelOverlay(overlayId: number): Promise<void> {
  return mutateAgentModels(`/api/admin/agent-models/${overlayId}`, {
    method: "DELETE",
  });
}
