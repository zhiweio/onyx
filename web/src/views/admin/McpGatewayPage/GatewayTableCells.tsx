"use client";

import { useTranslations } from "next-intl";
import { Tag, Text, type TagColor } from "@opal/components";

export {
  DateTimeCell,
  MetricCell,
  ServerTagCell,
  TruncatedTextCell,
} from "@/components/admin/TableCells";

export function outcomeColor(outcome: string): TagColor {
  switch (outcome) {
    case "hit":
      return "green";
    case "miss":
      return "amber";
    case "swr":
      return "blue";
    case "refresh":
      return "purple";
    case "error":
      return "red";
    default:
      return "gray";
  }
}

export function outcomeLabel(
  t: ReturnType<typeof useTranslations<"admin.mcpGateway">>,
  outcome: string
): string {
  switch (outcome) {
    case "hit":
      return t("calls.outcomes.hit");
    case "miss":
      return t("calls.outcomes.miss");
    case "swr":
      return t("calls.outcomes.swr");
    case "refresh":
      return t("calls.outcomes.refresh");
    case "bypass":
      return t("calls.outcomes.bypass");
    case "error":
      return t("calls.outcomes.error");
    default:
      return outcome;
  }
}

interface OutcomeTagProps {
  outcome: string;
}

export function OutcomeTag({ outcome }: OutcomeTagProps) {
  const t = useTranslations("admin.mcpGateway");
  return <Tag title={outcomeLabel(t, outcome)} color={outcomeColor(outcome)} />;
}

interface BilledTagProps {
  billed: boolean;
}

export function BilledTag({ billed }: BilledTagProps) {
  const t = useTranslations("admin.mcpGateway");
  return (
    <Tag
      title={billed ? t("calls.billedYes") : t("calls.billedNo")}
      color={billed ? "amber" : "gray"}
    />
  );
}

function refreshStatusColor(status: string): TagColor {
  switch (status) {
    case "ok":
      return "green";
    case "error":
    case "failed":
      return "red";
    case "pending":
    case "running":
      return "amber";
    default:
      return "gray";
  }
}

interface RefreshStatusTagProps {
  status: string | null | undefined;
  empty: string;
}

export function RefreshStatusTag({ status, empty }: RefreshStatusTagProps) {
  const t = useTranslations("admin.mcpGateway");
  if (!status) {
    return (
      <Text font="secondary-body" color="text-03">
        {empty}
      </Text>
    );
  }
  const label = (() => {
    switch (status) {
      case "ok":
        return t("cache.statuses.ok");
      case "error":
        return t("cache.statuses.error");
      case "failed":
        return t("cache.statuses.failed");
      case "pending":
        return t("cache.statuses.pending");
      default:
        return status;
    }
  })();
  return <Tag title={label} color={refreshStatusColor(status)} />;
}
