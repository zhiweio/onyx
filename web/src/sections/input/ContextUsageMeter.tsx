"use client";

import { useMemo } from "react";
import { useTranslations } from "next-intl";
import { Text, Tooltip } from "@opal/components";
import { cn } from "@opal/utils";

interface ContextUsageMeterProps {
  usedTokens: number;
  contextLimit: number | null;
}

const WARN = 0.7;
const CRIT = 0.9;

const SIZE = 16;
const STROKE = 2;
const R = (SIZE - STROKE) / 2;
const CIRC = 2 * Math.PI * R;

function formatTokenCount(tokens: number): string {
  if (tokens >= 1_000_000) {
    return `${(tokens / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
  }
  return tokens >= 1000 ? `${Math.round(tokens / 1000)}K` : `${tokens}`;
}

export default function ContextUsageMeter({
  usedTokens,
  contextLimit,
}: ContextUsageMeterProps) {
  const t = useTranslations("composer.contextUsage");
  const view = useMemo(() => {
    if (!contextLimit || contextLimit <= 0 || usedTokens <= 0) return null;
    const ratio = usedTokens / contextLimit;
    const pct = Math.min(ratio, 1);
    const displayPct = Math.min(Math.round(ratio * 100), 999);
    const level = pct >= CRIT ? "crit" : pct >= WARN ? "warn" : "ok";
    return { pct, displayPct, level };
  }, [usedTokens, contextLimit]);

  if (!view || !contextLimit) return null;

  const arcColor =
    view.level === "crit"
      ? "stroke-status-error-05"
      : view.level === "warn"
        ? "stroke-status-warning-05"
        : "stroke-text-04";

  const tooltip = t("tooltip", {
    used: formatTokenCount(usedTokens),
    limit: formatTokenCount(contextLimit),
    pct: view.displayPct,
  });

  return (
    <Tooltip tooltip={tooltip} side="top" align="end">
      <span
        className="flex items-center gap-1.5 select-none"
        role="img"
        aria-label={tooltip}
      >
        {view.level !== "ok" && (
          <Text font="secondary-body" color="text-03" nowrap>
            {`${view.displayPct}%`}
          </Text>
        )}
        <svg
          width={SIZE}
          height={SIZE}
          viewBox={`0 0 ${SIZE} ${SIZE}`}
          className="-rotate-90 shrink-0"
          aria-hidden
        >
          <circle
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={R}
            fill="none"
            strokeWidth={STROKE}
            className="stroke-border-03"
          />
          <circle
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={R}
            fill="none"
            strokeWidth={STROKE}
            strokeLinecap="round"
            strokeDasharray={CIRC}
            strokeDashoffset={CIRC * (1 - view.pct)}
            className={cn(
              arcColor,
              "transition-[stroke-dashoffset,stroke] duration-500 ease-out",
              "motion-reduce:transition-none"
            )}
          />
        </svg>
      </span>
    </Tooltip>
  );
}
