"use client";

import { useEffect, useState } from "react";

/**
 * Ticks `Date.now()` on an interval so relative labels ("5m", "3h") age in
 * place without a re-render per row.
 */
export function useTickingNow(intervalMs = 30_000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), intervalMs);
    return () => window.clearInterval(id);
  }, [intervalMs]);
  return now;
}
