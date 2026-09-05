"use client";

import { useTranslations } from "next-intl";
import useSWR from "swr";
import { Text } from "@opal/components";
import { cn } from "@opal/utils";
import { SWR_KEYS } from "@/lib/swr-keys";
import { errorHandlingFetcher } from "@/lib/fetcher";
import type { CraftJobResponse } from "@/app/craft/services/apiServices";

const IN_FLIGHT = new Set([
  "pending",
  "running",
  "waiting_specialists",
]);

export function isCraftJobInFlight(job?: CraftJobResponse | null): boolean {
  return !!job && IN_FLIGHT.has(job.status);
}

export function useCraftJob(sessionId: string | null) {
  return useSWR<CraftJobResponse>(
    sessionId ? SWR_KEYS.craftJob(sessionId) : null,
    errorHandlingFetcher,
    {
      revalidateOnFocus: false,
      refreshInterval: (data) => (isCraftJobInFlight(data) ? 5000 : 0),
      shouldRetryOnError: false,
    }
  );
}

export default function CraftJobBanner({
  sessionId,
}: {
  sessionId: string | null;
}) {
  const t = useTranslations("craft.longJob");
  const { data } = useCraftJob(sessionId);
  if (!data) return null;

  const phase = data.phases[data.current_phase_index];
  const label =
    data.status === "waiting_specialists"
      ? t("status.waitingSpecialists")
      : data.status === "running"
        ? t("status.running", {
            phase: phase?.name ?? phase?.id ?? String(data.current_phase_index + 1),
          })
        : data.status === "succeeded"
          ? t("status.succeeded")
          : data.status === "failed"
            ? t("status.failed")
            : t("status.cancelled");

  return (
    <div
      className={cn(
        "inline-flex min-w-0 max-w-full items-center",
        "overflow-hidden rounded-08 border border-border-01",
        "bg-background-tint-00 px-2 py-1"
      )}
      data-testid="craft-job-banner"
    >
      <Text font="secondary-body" color="text-03" nowrap>
        {`${t("label")}: ${label}`}
      </Text>
    </div>
  );
}
