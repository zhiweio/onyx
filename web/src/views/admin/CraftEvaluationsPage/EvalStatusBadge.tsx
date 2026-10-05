"use client";

import { useTranslations } from "next-intl";
import { cn } from "@opal/utils";
import { Text } from "@opal/components";
import { getEvalStatusDisplay } from "./utils";

interface EvalStatusBadgeProps {
  status: string;
}

/**
 * Icon + tinted-pill badge for an eval status (run or case level).
 * Visual language matches the craft `RunStatusBadge`.
 */
export default function EvalStatusBadge({ status }: EvalStatusBadgeProps) {
  const t = useTranslations("admin.craft.evaluations");
  const display = getEvalStatusDisplay(status);
  const Icon = display.icon;

  return (
    <div
      className={cn(
        "inline-flex items-center gap-1 px-1.5 py-0.5 rounded-08",
        display.badgeClassName
      )}
      data-testid={`eval-status-${status}`}
    >
      <Icon size={12} className={display.iconClassName} />
      <Text font="figure-small-label" color="text-03" nowrap>
        {t(`status.${status}`)}
      </Text>
    </div>
  );
}
