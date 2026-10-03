import { errorHandlingFetcher } from "@/lib/fetcher";

/**
 * One sandbox-driveable model. The `model_id` is the gateway wire id
 * (`<provider_id>/<model_name>`); the list is a read-only view over the
 * configured LLM providers (the "Model Providers" tab).
 */
export interface AgentModelView {
  model_id: string;
  provider_id: number;
  provider: string;
  display_name: string;
  context_window: number | null;
  max_output_tokens: number | null;
  runtimes: string[];
  is_default: boolean;
}

export interface AgentModelListResponse {
  models: AgentModelView[];
}

export function fetchAgentModels(): Promise<AgentModelListResponse> {
  return errorHandlingFetcher<AgentModelListResponse>(
    "/api/admin/agent-models"
  );
}
