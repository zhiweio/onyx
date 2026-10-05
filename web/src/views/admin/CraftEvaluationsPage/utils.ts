import type { TagColor } from "@opal/components/tag/colors";
import type { IconFunctionComponent } from "@opal/types";
import {
  SvgAlertCircle,
  SvgAlertTriangle,
  SvgCheckCircle,
  SvgClock,
  SvgLoader,
} from "@opal/icons";

/** "87%" for a 0–1 score, "–" when missing. */
export function formatScore(score: number | null | undefined): string {
  if (score === null || score === undefined) {
    return "–";
  }
  return `${(score * 100).toFixed(0)}%`;
}

/** "85s" / "12m" / "2h 30m" for a duration in seconds, "–" when missing. */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) {
    return "–";
  }
  if (seconds < 90) {
    return `${Math.round(seconds)}s`;
  }
  const minutes = Math.floor(seconds / 60);
  if (minutes < 90) {
    return `${minutes}m`;
  }
  const rem = minutes % 60;
  return rem === 0
    ? `${Math.floor(minutes / 60)}h`
    : `${Math.floor(minutes / 60)}h ${rem}m`;
}

/** Absolute local timestamp, used in tooltips. */
export function formatDateTime(value: string | null): string {
  if (!value) {
    return "–";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

// ---------------------------------------------------------------------------
// Status → badge visual mapping (mirrors the craft RunStatusBadge language)
// ---------------------------------------------------------------------------

export interface EvalStatusDisplay {
  icon: IconFunctionComponent;
  /** Tinted background class for the badge pill. */
  badgeClassName: string;
  /** Class for the icon only. */
  iconClassName: string;
}

export function getEvalStatusDisplay(status: string): EvalStatusDisplay {
  switch (status) {
    case "succeeded":
    case "pass":
      return {
        icon: SvgCheckCircle,
        badgeClassName: "bg-status-success-01",
        iconClassName: "text-status-success-05",
      };
    case "failed":
    case "error":
    case "fail":
      return {
        icon: SvgAlertCircle,
        badgeClassName: "bg-status-error-01",
        iconClassName: "text-status-error-05",
      };
    case "regressed":
      return {
        icon: SvgAlertTriangle,
        badgeClassName: "bg-status-warning-01",
        iconClassName: "text-status-warning-05",
      };
    case "running":
      return {
        icon: SvgLoader,
        badgeClassName: "bg-status-info-01",
        iconClassName: "text-status-info-05 animate-spin",
      };
    // queued / pending / unknown
    default:
      return {
        icon: SvgClock,
        badgeClassName: "bg-background-tint-02",
        iconClassName: "text-text-03",
      };
  }
}

/** Tag color for an LLM-judge verdict. */
export function getVerdictTagColor(verdict: string): TagColor {
  switch (verdict) {
    case "pass":
      return "green";
    case "partial":
      return "amber";
    case "fail":
      return "red";
    default:
      return "gray";
  }
}

/** Tag color for how a run was started. */
export function getTriggerTagColor(trigger: string): TagColor {
  return trigger === "nightly" ? "blue" : "gray";
}

/** i18n key suffix under `runs.triggerValue` — unknown triggers read as manual. */
export function getTriggerKey(trigger: string): "manual" | "nightly" {
  return trigger === "nightly" ? "nightly" : "manual";
}
