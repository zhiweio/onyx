"use client";

import { useTranslations } from "next-intl";
import useSWR from "swr";
import { Text } from "@opal/components";
import { cn } from "@opal/utils";
import { SWR_KEYS } from "@/lib/swr-keys";
import { errorHandlingFetcher } from "@/lib/fetcher";
import {
  cancelCraftJob,
  type CraftJobPhaseResponse,
  type CraftJobResponse,
} from "@/app/craft/services/apiServices";

const IN_FLIGHT = new Set(["pending", "running", "waiting_specialists"]);

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

function phaseTone(status: string): string {
  if (status === "succeeded") return "border-border-02 bg-background-tint-01";
  if (status === "running") return "border-border-01 bg-background-tint-02";
  if (status === "failed") return "border-border-01 bg-background-tint-00";
  return "border-border-00 bg-background-neutral-01";
}

export default function CraftJobBanner({
  sessionId,
}: {
  sessionId: string | null;
}) {
  const t = useTranslations("craft.longJob");
  const { data, mutate } = useCraftJob(sessionId);
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

  const onCancel = async () => {
    try {
      await cancelCraftJob(data.id);
      void mutate();
    } catch {
      void mutate();
    }
  };

  return (
    <div
      className={cn(
        "flex min-w-0 max-w-full flex-col gap-1",
        "overflow-hidden rounded-08 border border-border-01",
        "bg-background-tint-00 px-2 py-1"
      )}
      data-testid="craft-job-banner"
    >
      <div className="flex min-w-0 items-center gap-2">
        <Text font="secondary-body" color="text-03" nowrap>
          {`${t("label")}: ${label}`}
        </Text>
        {isCraftJobInFlight(data) && (
          <button
            type="button"
            data-testid="craft-job-cancel"
            className="shrink-0 text-xs text-text-03 underline"
            onClick={() => void onCancel()}
          >
            {t("cancel")}
          </button>
        )}
      </div>
      <div
        className="flex min-w-0 flex-wrap gap-1"
        data-testid="craft-job-phases"
      >
        {data.phases.map((item: CraftJobPhaseResponse, index) => (
          <span
            key={`${item.id}-${index}`}
            data-testid={`craft-job-phase-${item.id}`}
            data-status={item.status}
            className={cn(
              "rounded-04 border px-1.5 py-0.5 text-[11px] leading-4 text-text-03",
              phaseTone(item.status)
            )}
          >
            {item.name || item.id}
          </span>
        ))}
      </div>
    </div>
  );
}
