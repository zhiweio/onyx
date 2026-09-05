"use client";

import useSWR from "swr";
import { SWR_KEYS } from "@/lib/swr-keys";
import { errorHandlingFetcher } from "@/lib/fetcher";
import type { Scenario, ScenarioListResponse } from "@/lib/scenarios/types";

export default function useScenarios() {
  const { data, error, isLoading, mutate } = useSWR<ScenarioListResponse>(
    SWR_KEYS.scenarios,
    errorHandlingFetcher
  );

  return {
    data: data?.scenarios ?? [],
    error,
    isLoading,
    refresh: mutate,
  };
}

export function useScenario(scenarioId: string | undefined) {
  const { data, error, isLoading, mutate } = useSWR<Scenario>(
    scenarioId ? SWR_KEYS.scenario(scenarioId) : null,
    errorHandlingFetcher
  );

  return {
    data,
    error,
    isLoading,
    refresh: mutate,
  };
}
