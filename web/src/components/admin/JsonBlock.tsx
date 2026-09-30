"use client";

import { CopyButton } from "@opal/components";
import { formatJsonValue } from "@/lib/jsonDisplay";

interface JsonBlockProps {
  value: Record<string, unknown> | null;
  testId?: string;
}

/** Scrollable, copyable pretty-printed JSON panel for detail modals. */
export function JsonBlock({ value, testId }: JsonBlockProps) {
  const text = formatJsonValue(value);
  return (
    <div
      className="relative rounded-12 border border-border-01 bg-background-tint-00"
      data-testid={testId}
    >
      <div className="absolute end-2 top-2 z-1">
        <CopyButton size="xs" getCopyText={() => text} />
      </div>
      <pre className="max-h-72 overflow-auto whitespace-pre break-normal p-3 pe-10 font-secondary-mono text-text-03">
        {text}
      </pre>
    </div>
  );
}
