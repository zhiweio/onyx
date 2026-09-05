import { createSession } from "@/app/craft/services/apiServices";
import type { Scenario } from "@/lib/scenarios/types";

export async function startScenarioRun(scenario: Scenario): Promise<string> {
  const session = await createSession({
    name: scenario.name,
    scenarioId: scenario.id,
  });
  return session.id;
}
