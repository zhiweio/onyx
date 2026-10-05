"use client";

import { cn } from "@opal/utils";
import { Text } from "@opal/components";
import {
  SvgAlertCircle,
  SvgCheckCircle,
  SvgClock,
  SvgPauseCircle,
  SvgPlayCircle,
} from "@opal/icons";
import type {
  LoopHealth,
  LoopItemStatus,
  LoopOutputState,
  LoopState,
} from "@/app/craft/v1/loops/interfaces";

interface BadgeDisplay {
  label: string;
  icon: React.FunctionComponent<{ size?: number; className?: string }>;
  className: string;
  iconClassName: string;
}

// Labels are deliberately hard-coded English, matching the scheduled-task
// badges this feature mirrors.
function loopStateDisplay(state: LoopState): BadgeDisplay {
  switch (state) {
    case "enabled":
      return {
        label: "Enabled",
        icon: SvgPlayCircle,
        className: "bg-status-success-01",
        iconClassName: "text-status-success-05",
      };
    case "paused":
    case "archived":
      return {
        label: state === "paused" ? "Paused" : "Archived",
        icon: SvgPauseCircle,
        className: "bg-background-tint-02",
        iconClassName: "text-text-03",
      };
    case "quarantined":
      return {
        label: "Quarantined",
        icon: SvgAlertCircle,
        className: "bg-status-error-01",
        iconClassName: "text-status-error-05",
      };
  }
}

export function LoopStateBadge({ state }: { state: LoopState }) {
  return <Badge {...loopStateDisplay(state)} testId={`loop-state-${state}`} />;
}

function healthDisplay(health: LoopHealth): BadgeDisplay {
  switch (health) {
    case "healthy":
      return {
        label: "Healthy",
        icon: SvgCheckCircle,
        className: "bg-status-success-01",
        iconClassName: "text-status-success-05",
      };
    case "degraded":
      return {
        label: "Degraded",
        icon: SvgAlertCircle,
        className: "bg-status-warning-01",
        iconClassName: "text-status-warning-05",
      };
    case "failing":
    case "quarantined":
      return {
        label: health === "failing" ? "Failing" : "Quarantined",
        icon: SvgAlertCircle,
        className: "bg-status-error-01",
        iconClassName: "text-status-error-05",
      };
  }
}

export function LoopHealthBadge({ health }: { health: LoopHealth }) {
  return <Badge {...healthDisplay(health)} testId={`loop-health-${health}`} />;
}

function itemStatusDisplay(status: LoopItemStatus): BadgeDisplay {
  switch (status) {
    case "queued":
      return {
        label: "Queued",
        icon: SvgClock,
        className: "bg-background-tint-02",
        iconClassName: "text-text-03",
      };
    case "in_progress":
      return {
        label: "Running",
        icon: SvgClock,
        className: "bg-status-info-01",
        iconClassName: "text-status-info-05",
      };
    case "ready":
      return {
        label: "Ready",
        icon: SvgCheckCircle,
        className: "bg-status-success-01",
        iconClassName: "text-status-success-05",
      };
    case "shipped":
      return {
        label: "Shipped",
        icon: SvgCheckCircle,
        className: "bg-background-tint-02",
        iconClassName: "text-text-03",
      };
    case "failed":
      return {
        label: "Failed",
        icon: SvgAlertCircle,
        className: "bg-status-error-01",
        iconClassName: "text-status-error-05",
      };
    case "skipped":
      return {
        label: "Skipped",
        icon: SvgClock,
        className: "bg-background-tint-02",
        iconClassName: "text-text-03",
      };
  }
}

export function LoopItemStatusBadge({ status }: { status: LoopItemStatus }) {
  return (
    <Badge {...itemStatusDisplay(status)} testId={`item-status-${status}`} />
  );
}

function outputStateDisplay(state: LoopOutputState): BadgeDisplay {
  switch (state) {
    case "staged":
      return {
        label: "Staged",
        icon: SvgClock,
        className: "bg-background-tint-02",
        iconClassName: "text-text-03",
      };
    case "ready":
      return {
        label: "Awaiting decision",
        icon: SvgClock,
        className: "bg-status-warning-01",
        iconClassName: "text-status-warning-05",
      };
    case "shipping":
      return {
        label: "Shipping",
        icon: SvgClock,
        className: "bg-status-info-01",
        iconClassName: "text-status-info-05",
      };
    case "shipped":
      return {
        label: "Shipped",
        icon: SvgCheckCircle,
        className: "bg-status-success-01",
        iconClassName: "text-status-success-05",
      };
    case "returned":
      return {
        label: "Returned",
        icon: SvgAlertCircle,
        className: "bg-status-error-01",
        iconClassName: "text-status-error-05",
      };
  }
}

export function LoopOutputStateBadge({ state }: { state: LoopOutputState }) {
  return (
    <Badge {...outputStateDisplay(state)} testId={`output-state-${state}`} />
  );
}

function Badge({
  label,
  icon: Icon,
  className,
  iconClassName,
  testId,
}: BadgeDisplay & { testId: string }) {
  return (
    <div
      className={cn(
        "inline-flex items-center gap-1 px-1.5 py-0.5 rounded-08",
        className
      )}
      data-testid={testId}
    >
      <Icon size={12} className={iconClassName} />
      <Text font="figure-small-label" color="text-03">
        {label}
      </Text>
    </div>
  );
}
