"use client";

import { useTranslations } from "next-intl";
import { LineItemButton, Popover, SelectButton } from "@opal/components";
import type { ReasoningEffortOverride } from "@/lib/languageModels/types";
import {
  COMPOSER_THOUGHT_STOPS,
  DEFAULT_THOUGHT_LEVEL,
  allowedComposerStop,
  composerStopIndex,
  toComposerThoughtLevel,
} from "@/sections/input/thoughtLevel";
import SvgThoughtBrain from "@/sections/input/thoughtLevelIcon";

const THOUGHT_LABEL_KEYS = {
  off: "off",
  low: "low",
  medium: "medium",
  high: "high",
  xhigh: "max",
} as const satisfies Record<ReasoningEffortOverride, string>;

interface ThoughtLevelSelectProps {
  value: ReasoningEffortOverride | null;
  onChange: (effort: ReasoningEffortOverride) => void;
  supportsReasoning: boolean;
  supportedEfforts?: ReasoningEffortOverride[];
  effortMax?: ReasoningEffortOverride | null;
  fallback?: ReasoningEffortOverride | null;
  disabled?: boolean;
}

export default function ThoughtLevelSelect({
  value,
  onChange,
  supportsReasoning,
  effortMax,
  fallback = DEFAULT_THOUGHT_LEVEL,
  disabled = false,
}: ThoughtLevelSelectProps) {
  const t = useTranslations("composer.thoughtLevel");
  const allowedStop = allowedComposerStop(effortMax);
  const options = COMPOSER_THOUGHT_STOPS;

  const pickAllowed = (effort: ReasoningEffortOverride | null | undefined) => {
    const normalized = toComposerThoughtLevel(effort);
    return normalized != null && composerStopIndex(normalized) <= allowedStop
      ? normalized
      : null;
  };

  const defaultAllowed =
    [...options]
      .reverse()
      .find((effort) => composerStopIndex(effort) <= allowedStop) ??
    options[0];

  if (!supportsReasoning) return null;

  const current =
    pickAllowed(value) ??
    pickAllowed(fallback) ??
    defaultAllowed ??
    DEFAULT_THOUGHT_LEVEL;
  const currentLabel = t(`levels.${THOUGHT_LABEL_KEYS[current]}.label`);

  return (
    <Popover>
      <Popover.Trigger asChild>
        <SelectButton
          disabled={disabled}
          icon={SvgThoughtBrain}
          tooltip={t("tooltip")}
          foldable
        >
          {currentLabel}
        </SelectButton>
      </Popover.Trigger>
      <Popover.Content width="fit" align="end">
        <Popover.Menu>
          {options.map((effort) => {
            const aboveCap = composerStopIndex(effort) > allowedStop;
            return (
              <LineItemButton
                key={effort}
                sizePreset="main-ui"
                rounding={2}
                disabled={aboveCap}
                state={effort === current ? "selected" : "empty"}
                selectVariant={
                  effort === current ? "select-heavy" : "select-light"
                }
                title={t(`levels.${THOUGHT_LABEL_KEYS[effort]}.label`)}
                onClick={() => {
                  if (!aboveCap) onChange(effort);
                }}
              />
            );
          })}
        </Popover.Menu>
      </Popover.Content>
    </Popover>
  );
}
