"use client";

import { useTranslations } from "next-intl";

export default function LongJobToggle({
  checked,
  disabled = false,
  onChange,
}: {
  checked: boolean;
  disabled?: boolean;
  onChange: (enabled: boolean) => void;
}) {
  const t = useTranslations("craft.longJob");
  return (
    <label className="flex items-center gap-1.5 text-xs text-text-03">
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        data-testid="craft-long-job-toggle"
        onChange={(event) => onChange(event.target.checked)}
      />
      {t("toggle")}
    </label>
  );
}
