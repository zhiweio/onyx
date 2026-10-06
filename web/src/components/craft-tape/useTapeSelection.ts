"use client";

import { useCallback } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import type { Route } from "next";

/**
 * Master-detail selection synced to `?sessionId=`: refresh keeps the detail,
 * links carry it, and clearing the selection clears the param (the old pages
 * kept the selection in component state, so it died with the render).
 */
export function useTapeSelection(): {
  selectedId: string | null;
  select: (sessionId: string | null) => void;
} {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const selectedId = searchParams.get("sessionId");

  const select = useCallback(
    (sessionId: string | null) => {
      const params = new URLSearchParams(searchParams.toString());
      if (sessionId) params.set("sessionId", sessionId);
      else params.delete("sessionId");
      const query = params.toString();
      const url = query ? `${pathname}?${query}` : pathname;
      router.replace(url as Route, { scroll: false });
    },
    [router, pathname, searchParams]
  );

  return { selectedId, select };
}
