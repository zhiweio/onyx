"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Text } from "@opal/components";
import ShimmerText from "@/refresh-components/texts/ShimmerText";

/**
 * Header for the running turn: elapsed work timer in ZCode's style
 * ("Working for 1m 20s"), shown above the live tail while the agent runs.
 */

function formatDuration(totalSeconds: number): string {
  // ZCode convention: at least 1s, at most two unit parts (d/h/m/s).
  const seconds = Math.max(1, Math.round(totalSeconds));
  const parts: string[] = [];
  let remaining = seconds;
  for (const [unit, size] of [
    ["d", 86400],
    ["h", 3600],
    ["m", 60],
    ["s", 1],
  ] as const) {
    if (parts.length === 2) break;
    const value = Math.floor(remaining / size);
    if (value > 0 || parts.length > 0) {
      parts.push(`${value}${unit}`);
      remaining -= value * size;
    }
  }
  return parts.join(" ");
}

interface TurnStatusHeaderProps {
  /** Epoch ms when the turn started. */
  startedAtMs: number;
  running: boolean;
}

export function TurnStatusHeader({
  startedAtMs,
  running,
}: TurnStatusHeaderProps) {
  const t = useTranslations("craft.timeline");
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  useEffect(() => {
    if (!running) {
      return;
    }
    const tick = () => {
      setElapsedSeconds(Math.max(0, (Date.now() - startedAtMs) / 1000));
    };
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [running, startedAtMs]);

  if (!running) {
    return null;
  }

  return (
    <div
      className="flex items-center gap-2 pb-1"
      data-testid="craft-turn-status"
    >
      <ShimmerText>
        {t("workingFor", { duration: formatDuration(elapsedSeconds) })}
      </ShimmerText>
    </div>
  );
}
