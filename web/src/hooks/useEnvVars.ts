"use client";

import useSWR from "swr";
import { SWR_KEYS } from "@/lib/swr-keys";
import { errorHandlingFetcher } from "@/lib/fetcher";
import type { EnvVarListResponse } from "@/app/craft/v1/env-vars/interfaces";

/**
 * Env vars / secrets the caller may grant to a task.
 *
 * - `projectId` set: the caller's user-scope rows plus that project's rows
 *   (task-form picker mode — matches what the backend will accept as grants).
 * - unset: user-scope rows plus every readable project's rows
 *   (management-page mode).
 */
export function useEnvVars(projectId?: string | null) {
  const key =
    projectId != null
      ? SWR_KEYS.envVarsForProject(projectId)
      : SWR_KEYS.envVarsAllProjects;
  const { data, error, isLoading, mutate } = useSWR<EnvVarListResponse>(
    key,
    errorHandlingFetcher
  );

  return {
    data: data?.items ?? [],
    error,
    isLoading,
    refresh: mutate,
  };
}
