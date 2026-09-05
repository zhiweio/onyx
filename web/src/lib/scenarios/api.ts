import type {
  Scenario,
  ScenarioListResponse,
  ScenarioRules,
  ScenarioSharePermission,
} from "@/lib/scenarios/types";

const SCENARIOS_URL = "/api/scenarios";

async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") {
      return body.detail;
    }
  } catch {
    // ignore
  }
  return `Request failed: ${response.status}`;
}

async function handle<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export async function listScenarios(): Promise<Scenario[]> {
  const response = await fetch(SCENARIOS_URL);
  const payload = await handle<ScenarioListResponse>(response);
  return payload.scenarios;
}

export async function getScenario(scenarioId: string): Promise<Scenario> {
  const response = await fetch(`${SCENARIOS_URL}/${scenarioId}`);
  return handle<Scenario>(response);
}

export async function createScenario(input: {
  name: string;
  description: string;
  skill_ids: string[];
  rules?: ScenarioRules;
  report_template?: string | null;
}): Promise<Scenario> {
  const response = await fetch(SCENARIOS_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return handle<Scenario>(response);
}

export async function updateScenario(
  scenarioId: string,
  input: {
    name?: string;
    description?: string;
    skill_ids?: string[];
    rules?: ScenarioRules;
    report_template?: string | null;
  }
): Promise<Scenario> {
  const response = await fetch(`${SCENARIOS_URL}/${scenarioId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return handle<Scenario>(response);
}

export async function duplicateScenario(scenarioId: string): Promise<Scenario> {
  const response = await fetch(`${SCENARIOS_URL}/${scenarioId}/duplicate`, {
    method: "POST",
  });
  return handle<Scenario>(response);
}

export async function shareScenario(
  scenarioId: string,
  input: {
    user_ids: string[];
    group_ids: number[];
    public_permission: ScenarioSharePermission | null;
  }
): Promise<Scenario> {
  const response = await fetch(`${SCENARIOS_URL}/${scenarioId}/share`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return handle<Scenario>(response);
}

export async function deleteScenario(scenarioId: string): Promise<void> {
  const response = await fetch(`${SCENARIOS_URL}/${scenarioId}`, {
    method: "DELETE",
  });
  await handle<void>(response);
}
