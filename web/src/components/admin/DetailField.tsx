"use client";

import { Card, CopyButton, Text } from "@opal/components";

interface DetailFieldProps {
  label: string;
  value: string | null | undefined;
  empty: string;
  copyable?: boolean;
}

/** Read-only label/value card used inside detail modals. */
export function DetailField({
  label,
  value,
  empty,
  copyable = false,
}: DetailFieldProps) {
  const display = value || empty;
  const canCopy = copyable && Boolean(value);

  return (
    <Card padding={2} rounding={3} background="heavy">
      <div className="flex min-w-0 flex-col gap-1">
        <Text as="p" font="secondary-body" color="text-03">
          {label}
        </Text>
        <div className="flex min-w-0 items-start gap-1">
          <Text
            as="p"
            font="secondary-mono"
            color={value ? "text-05" : "text-03"}
            wordWrap="break-all"
          >
            {display}
          </Text>
          {canCopy ? (
            <CopyButton size="xs" getCopyText={() => value ?? ""} />
          ) : null}
        </div>
      </div>
    </Card>
  );
}
