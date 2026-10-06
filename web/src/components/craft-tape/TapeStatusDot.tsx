"use client";

import { useEffect, useRef } from "react";
import type { TapeStatus } from "./tapeStatus";

const DOT_COLORS: Record<Exclude<TapeStatus, "running">, string> = {
  done: "text-green-500",
  warning: "text-amber-500",
  error: "text-red-600 dark:text-red-400",
  idle: "text-neutral-300 dark:text-neutral-600",
};

/**
 * dsh StateDot port: solid states are a 10px dot with a 6px currentColor core;
 * `running` is a 14px spinner (quiet track + breathing arc). All animations
 * pin to document time zero on mount/update so every visible spinner stays in
 * phase, and globals.css drops the motion under `prefers-reduced-motion`.
 */
export default function TapeStatusDot({
  status,
  className = "",
}: {
  status: TapeStatus;
  className?: string;
}) {
  const spinnerRef = useRef<SVGSVGElement | null>(null);

  useEffect(() => {
    const element = spinnerRef.current;
    if (!element || typeof element.getAnimations !== "function") return;
    for (const animation of element.getAnimations({ subtree: true })) {
      animation.startTime = 0;
    }
  });

  if (status === "running") {
    return (
      <svg
        ref={spinnerRef}
        className={`tape-dot-spinner h-3.5 w-3.5 text-neutral-400 dark:text-neutral-500 ${className}`}
        viewBox="0 0 24 24"
        aria-hidden="true"
        data-testid="tape-status-running"
      >
        <g className="tape-dot-spinner-motion">
          <circle className="tape-dot-spinner-track" cx="12" cy="12" r="9.5" />
          <circle className="tape-dot-spinner-arc" cx="12" cy="12" r="9.5" />
        </g>
      </svg>
    );
  }
  return (
    <span
      className={`relative inline-flex h-2.5 w-2.5 flex-none ${DOT_COLORS[status]} ${className}`}
      aria-hidden="true"
      data-testid={`tape-status-${status}`}
    >
      <span className="absolute inset-[20%] rounded-full bg-current" />
    </span>
  );
}
