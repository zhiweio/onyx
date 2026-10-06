"use client";

/**
 * Right-edge turn rail — the dsh TurnNavigator scaled to tapes: one mark per
 * recorded turn with its status color and index, a hover preview (model,
 * duration, tokens, outcome), and a click that scopes the trajectory ledger
 * (or replay) to that turn.
 */

import { useTranslations } from "next-intl";
import { Tooltip } from "@opal/components";
import { cn } from "@opal/utils";
import type { TapeTurnItem } from "@/lib/craft-tape/types";
import { formatDuration, formatTokenCount, isKnownReason } from "./constants";
import { turnTapeStatus } from "./tapeStatus";
import TapeStatusDot from "./TapeStatusDot";

export default function TapeTurnRail({
  turns,
  activeTurn,
  onSelectTurn,
}: {
  turns: TapeTurnItem[];
  activeTurn: number | null;
  onSelectTurn: (turnIndex: number | null) => void;
}) {
  const t = useTranslations("craftTape");
  if (turns.length === 0) return null;

  return (
    <div
      className="flex w-12 flex-none flex-col items-center gap-0.5 overflow-y-auto border-l border-neutral-200 py-2 dark:border-neutral-700"
      data-testid="tape-turn-rail"
    >
      {turns.map((turn) => {
        const status = turnTapeStatus(turn);
        const active = turn.turn_index === activeTurn;
        const duration = formatDuration(turn.started_at, turn.ended_at);
        return (
          <Tooltip
            key={turn.turn_index}
            side="left"
            delayDuration={300}
            tooltip={
              <div className="flex flex-col gap-0.5">
                <div className="text-sm font-medium">
                  {t("turns.turn")} #{turn.turn_index}
                </div>
                {turn.model ? (
                  <div className="text-xs opacity-80">{turn.model}</div>
                ) : null}
                {duration ? (
                  <div className="text-xs opacity-80">{duration}</div>
                ) : null}
                <div className="text-xs opacity-80">
                  {t("detail.tokens", {
                    count: formatTokenCount(turn.output_tokens),
                  })}
                </div>
                <div className="flex items-center gap-2 text-xs opacity-80">
                  <TapeStatusDot status={status} />
                  {turn.turn_end_reason
                    ? isKnownReason(turn.turn_end_reason)
                      ? t(`reasons.${turn.turn_end_reason}`)
                      : turn.turn_end_reason
                    : t("status.running")}
                </div>
              </div>
            }
          >
            <button
              type="button"
              className={cn(
                "flex h-6 w-9 items-center justify-center gap-1 rounded-md font-mono text-[10px]",
                active
                  ? "bg-neutral-200 text-neutral-900 dark:bg-neutral-700 dark:text-neutral-100"
                  : "text-neutral-500 hover:bg-neutral-100 dark:text-neutral-400 dark:hover:bg-neutral-800"
              )}
              onClick={() => onSelectTurn(active ? null : turn.turn_index)}
              aria-pressed={active}
              data-testid={`tape-rail-turn-${turn.turn_index}`}
            >
              <TapeStatusDot status={status} />
              {turn.turn_index}
            </button>
          </Tooltip>
        );
      })}
    </div>
  );
}
