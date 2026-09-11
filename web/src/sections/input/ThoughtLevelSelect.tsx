"use client";

import { useMemo } from "react";
import { useTranslations } from "next-intl";
import { LineItemButton, Popover, SelectButton } from "@opal/components";
import { SvgLightbulbSimple } from "@opal/icons";
import type { ReasoningEffortOverride } from "@/lib/languageModels/types";
import {
  ALL_REASONING_STOPS,
  cappedReasoningStop,
  maxReasoningStop,
} from "@/sections/model-selector/setting-controls";

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
  supportedEfforts,
  effortMax,
  fallback,
  disabled = false,
}: ThoughtLevelSelectProps) {
  const t = useTranslations("composer.thoughtLevel");
  const capabilityStop = maxReasoningStop(supportedEfforts);
  const maxStop = cappedReasoningStop(capabilityStop, effortMax);
  const options = useMemo(
    () => ALL_REASONING_STOPS.slice(0, maxStop + 1),
    [maxStop]
  );

  if (!supportsReasoning || maxStop < 0) return null;

  const current =
    value && options.includes(value)
      ? value
      : fallback && options.includes(fallback)
        ? fallback
        : options[0];
  const currentLabel = current
    ? t(`levels.${THOUGHT_LABEL_KEYS[current]}.label`)
    : t("levels.low.label");

  return (
    <Popover>
      <Popover.Trigger asChild>
        <SelectButton
          disabled={disabled}
          icon={SvgLightbulbSimple}
          tooltip={t("tooltip")}
          foldable
        >
          {currentLabel}
        </SelectButton>
      </Popover.Trigger>
      <Popover.Content width="fit" align="end">
        <Popover.Menu>
          {options.map((effort) => (
            <LineItemButton
              key={effort}
              sizePreset="main-ui"
              rounding={2}
              state={effort === current ? "selected" : "empty"}
              selectVariant={effort === current ? "select-heavy" : "select-light"}
              title={t(`levels.${THOUGHT_LABEL_KEYS[effort]}.label`)}
              onClick={() => onChange(effort)}
            />
          ))}
        </Popover.Menu>
      </Popover.Content>
    </Popover>
  );
}
