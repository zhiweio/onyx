"use client";

import { useTranslations } from "next-intl";
import { SvgHistory } from "@opal/icons";

/**
 * Detail-pane placeholder when no session is selected — the master-detail
 * entry state (dsh never shows one because its conversation is always
 * present; a tape browser needs this empty state).
 */
export default function TapeNoSelection() {
  const t = useTranslations("craftTape");
  return (
    <div
      className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center"
      data-testid="tape-no-selection"
    >
      <SvgHistory className="h-8 w-8 text-neutral-300 dark:text-neutral-600" />
      <span className="text-sm font-medium text-neutral-500 dark:text-neutral-400">
        {t("browser.noSelectionTitle")}
      </span>
      <span className="max-w-xs text-xs text-neutral-400">
        {t("browser.noSelectionHint")}
      </span>
    </div>
  );
}
