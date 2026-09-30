"use client";

import { StandardAnswerCategory } from "@/lib/types";

/**
 * Community Edition stub. Standard answers belong to the Enterprise Edition,
 * which this build does not ship; consumers render their CE fallback path
 * (empty category list) instead.
 */
export function useStandardAnswerCategories(): {
  data: StandardAnswerCategory[] | null;
  isLoading: boolean;
  error: string | null;
} {
  return { data: null, isLoading: false, error: null };
}
