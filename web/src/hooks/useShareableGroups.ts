"use client";

import useSWR, { mutate } from "swr";
import { errorHandlingFetcher } from "@/lib/fetcher";
import { SWR_KEYS } from "@/lib/swr-keys";

export interface MinimalUserGroupSnapshot {
  id: number;
  name: string;
}

export default function useShareableGroups() {
  const { data, error, isLoading } = useSWR<MinimalUserGroupSnapshot[]>(
    SWR_KEYS.shareableGroups,
    errorHandlingFetcher
  );

  const refreshShareableGroups = () => mutate(SWR_KEYS.shareableGroups);

  return {
    data,
    isLoading,
    error,
    refreshShareableGroups,
  };
}
