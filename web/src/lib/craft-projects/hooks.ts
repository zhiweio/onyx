"use client";

import { useCallback } from "react";
import useSWR, { useSWRConfig } from "swr";
import { SWR_KEYS } from "@/lib/swr-keys";
import { errorHandlingFetcher } from "@/lib/fetcher";
import { projectNeedsRefresh } from "@/lib/craft-projects/display";
import type {
  CraftProject,
  CraftProjectListResponse,
} from "@/lib/craft-projects/types";

export function useRefreshCraftProjects() {
  const { mutate } = useSWRConfig();
  return useCallback(
    async (projectId?: string) => {
      await mutate(SWR_KEYS.craftProjects);
      if (projectId) {
        await mutate(SWR_KEYS.craftProject(projectId));
      }
    },
    [mutate]
  );
}

export function useCraftProjects() {
  const { data, error, isLoading, mutate } = useSWR<CraftProjectListResponse>(
    SWR_KEYS.craftProjects,
    errorHandlingFetcher
  );

  return {
    data: data?.projects ?? [],
    error,
    isLoading,
    refresh: mutate,
  };
}

export function useCraftProject(projectId: string | undefined) {
  const { data, error, isLoading, mutate } = useSWR<CraftProject>(
    projectId ? SWR_KEYS.craftProject(projectId) : null,
    errorHandlingFetcher,
    {
      refreshInterval: (latest) => (projectNeedsRefresh(latest) ? 5000 : 0),
    }
  );

  return {
    data,
    error,
    isLoading,
    refresh: mutate,
  };
}
