"use client";

import { useTranslations } from "next-intl";
import { Tag, Text } from "@opal/components";
import { useEnvVars } from "@/hooks/useEnvVars";

interface EnvVarSummaryProps {
  /** The task's project; ``null`` means only personal vars are grantable. */
  projectId: string | null;
  envVarIds: string[];
}

/** Read-only grant list for the task detail page (name tags, never values). */
export default function EnvVarSummary({
  projectId,
  envVarIds,
}: EnvVarSummaryProps) {
  const t = useTranslations("craft.tasks.envVarPicker");
  const { data: envVars, error, isLoading } = useEnvVars(projectId);
  const hasIds = envVarIds.length > 0;

  if (!hasIds) return null;
  // Wait for names so the tags never flash raw id fallbacks.
  if (isLoading) return null;

  const byId = new Map(envVars.map((item) => [item.id, item]));

  return (
    <div className="flex flex-col gap-2">
      <Text font="main-ui-action" color="text-03">
        {t("summary.title")}
      </Text>
      {error && (
        <Text font="secondary-body" color="status-error-05">
          {t("summary.partialLoadFailed")}
        </Text>
      )}
      <div className="flex flex-wrap gap-2">
        {envVarIds.map((id) => {
          const item = byId.get(id);
          if (!item && error) return null;
          const name = item?.name ?? t("staleFallbackName", { id });
          return (
            <Tag
              key={id}
              title={
                item?.is_secret ? name : `${name} — ${t("status.variable")}`
              }
            />
          );
        })}
      </div>
    </div>
  );
}
