"use client";

import useSWR from "swr";

import { SWR_KEYS } from "@/lib/swr-keys";
import { StandardAnswerCategory } from "@/lib/types";
import { errorHandlingFetcher } from "@/lib/fetcher";

/**
 * Standard answers are a CE feature in this build; the admin category list
 * backs the bots channel config picker.
 */
export function useStandardAnswerCategories(): {
  data: StandardAnswerCategory[] | null;
  isLoading: boolean;
  error: string | null;
} {
  const { data, isLoading, error } = useSWR<StandardAnswerCategory[]>(
    SWR_KEYS.adminStandardAnswerCategories,
    errorHandlingFetcher,
    { revalidateOnFocus: false }
  );

  return {
    data: data ?? null,
    isLoading,
    error: error ? String(error) : null,
  };
}
