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
  const seconds = Math.max(0, Math.floor(totalSeconds));
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  if (hours > 0) {
    return `${hours}h ${minutes % 60}m`;
  }
  if (minutes > 0) {
    return `${minutes}m ${seconds % 60}s`;
  }
  return `${seconds}s`;
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
