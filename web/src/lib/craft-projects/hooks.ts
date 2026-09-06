"use client";

import useSWR from "swr";
import { SWR_KEYS } from "@/lib/swr-keys";
import { errorHandlingFetcher } from "@/lib/fetcher";
import type { CraftProject, CraftProjectListResponse } from "@/lib/craft-projects/types";

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
    errorHandlingFetcher
  );

  return {
    data,
    error,
    isLoading,
    refresh: mutate,
  };
}
