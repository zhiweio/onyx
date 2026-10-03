import { ReadonlyURLSearchParams } from "next/navigation";

// search params for build pages
export const CRAFT_SEARCH_PARAM_NAMES = {
  SESSION_ID: "sessionId",
  SCENARIO_ID: "scenarioId",
};

export function getSessionIdFromSearchParams(
  searchParams: ReadonlyURLSearchParams | null
): string | null {
  return searchParams?.get(CRAFT_SEARCH_PARAM_NAMES.SESSION_ID) ?? null;
}

export function getScenarioIdFromSearchParams(
  searchParams: ReadonlyURLSearchParams | null
): string | null {
  return searchParams?.get(CRAFT_SEARCH_PARAM_NAMES.SCENARIO_ID) ?? null;
}
