import type { ReasoningEffortOverride } from "@/lib/languageModels/types";

/** Composer scale: Off, Low, Medium, Max. High is not offered. */
export const COMPOSER_THOUGHT_STOPS: ReasoningEffortOverride[] = [
  "off",
  "low",
  "medium",
  "xhigh",
];

export const DEFAULT_THOUGHT_LEVEL: ReasoningEffortOverride = "xhigh";

export function toComposerThoughtLevel(
  effort: ReasoningEffortOverride | null | undefined
): ReasoningEffortOverride | null {
  if (effort == null) return null;
  if (effort === "high") return "xhigh";
  return COMPOSER_THOUGHT_STOPS.includes(effort) ? effort : null;
}

export function composerStopIndex(
  effort: ReasoningEffortOverride | null | undefined
): number {
  const normalized = toComposerThoughtLevel(effort);
  return normalized ? COMPOSER_THOUGHT_STOPS.indexOf(normalized) : -1;
}

export function allowedComposerStop(
  effortMax: ReasoningEffortOverride | null | undefined
): number {
  const cap = composerStopIndex(effortMax);
  return cap >= 0 ? cap : COMPOSER_THOUGHT_STOPS.length - 1;
}
