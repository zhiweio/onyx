"use client";

import { Tag } from "@opal/components";
import { useTranslations } from "next-intl";
import { isKnownReason, reasonTagColor } from "./constants";

/**
 * Turn-outcome chip: known reasons localize, unknown reasons pass through
 * raw, and a missing reason means the turn never closed (interrupted).
 */
export default function ReasonTag({ reason }: { reason: string | null }) {
  const t = useTranslations("craftTape");
  const label =
    reason === null
      ? t("reasons.interrupted")
      : isKnownReason(reason)
        ? t(`reasons.${reason}`)
        : reason;
  return <Tag title={label} color={reasonTagColor(reason)} />;
}
