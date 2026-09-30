"use client";

import { useFormatter } from "next-intl";
import { Tag, Text, Tooltip } from "@opal/components";

interface DateTimeCellProps {
  value: string;
  timeStyle?: "short" | "medium";
}

export function DateTimeCell({
  value,
  timeStyle = "medium",
}: DateTimeCellProps) {
  const format = useFormatter();
  const date = new Date(value);
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <Text font="secondary-body" color="text-03" nowrap>
        {format.dateTime(date, { dateStyle: "short" })}
      </Text>
      <Text font="secondary-mono" color="text-04" nowrap>
        {format.dateTime(date, { timeStyle })}
      </Text>
    </div>
  );
}

interface TruncatedTextCellProps {
  value: string | null | undefined;
  empty: string;
  mono?: boolean;
}

export function TruncatedTextCell({
  value,
  empty,
  mono = false,
}: TruncatedTextCellProps) {
  if (!value) {
    return (
      <Text font="secondary-body" color="text-03">
        {empty}
      </Text>
    );
  }
  return (
    <Tooltip tooltip={value}>
      <div className="min-w-0 max-w-full overflow-hidden">
        <Text
          font={mono ? "secondary-mono" : "secondary-body"}
          color="text-04"
          nowrap
          maxLines={1}
        >
          {value}
        </Text>
      </div>
    </Tooltip>
  );
}

interface MetricCellProps {
  value: string;
}

export function MetricCell({ value }: MetricCellProps) {
  return (
    <Text font="secondary-mono" color="text-04" nowrap>
      {value}
    </Text>
  );
}

interface ServerTagCellProps {
  value: string | null | undefined;
  empty: string;
}

export function ServerTagCell({ value, empty }: ServerTagCellProps) {
  if (!value) {
    return (
      <Text font="secondary-body" color="text-03">
        {empty}
      </Text>
    );
  }
  return <Tag title={value} truncate tooltip={value} />;
}
