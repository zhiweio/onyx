"use client";

import { useCallback, useState } from "react";

export function useExtendTheme() {
  const [isDark, setIsDark] = useState(false);
  const onIsDarkChange = useCallback((next: boolean) => {
    setIsDark(next);
  }, []);
  return { isDark, onIsDarkChange };
}
