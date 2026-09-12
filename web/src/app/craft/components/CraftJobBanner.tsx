"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import useSWR from "swr";
import { Button, Popover, Tag, Text } from "@opal/components";
import { Content, ContentAction } from "@opal/layouts";
import { SvgAlertTriangle, SvgChevronDown, SvgHourglass } from "@opal/icons";
import { cn } from "@opal/utils";
import { SWR_KEYS } from "@/lib/swr-keys";
import { errorHandlingFetcher } from "@/lib/fetcher";
import {
  cancelCraftJob,
  type CraftJobPhaseResponse,
  type CraftJobResponse,
  type CraftJobSpecialistResponse,
  type CraftJobTimelineItem,
} from "@/app/craft/services/apiServices";
import {
  compactJobError,
  jobErrorDisplay,
  jobStatusTagColor,
  phaseTagColor,
  specialistRoleKey,
} from "@/lib/craft-jobs/display";
import { isKnownSessionRole } from "@/lib/craft-projects/display";

const IN_FLIGHT = new Set([
  "pending",
  "running",
  "waiting_specialists",
  "waiting_lanes",
  "interrupted",
]);

function hasOpenSpecialists(job: CraftJobResponse): boolean {
  return job.specialists.some(
    (specialist) =>
      specialist.status === "pending" || specialist.status === "running"
  );
}

export function isCraftJobInFlight(job?: CraftJobResponse | null): boolean {
  if (!job) return false;
  if (IN_FLIGHT.has(job.status)) return true;
  // A prior cancel can leave specialist lanes running. Keep the stop
  // control until those sessions are interrupted.
  return job.status === "cancelled" && hasOpenSpecialists(job);
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

function timelineLabel(
  item: CraftJobTimelineItem | CraftJobPhaseResponse,
  t: ReturnType<typeof useTranslations>
): string {
  if (item.kind === "plan") return t("timeline.plan");
  if (item.kind === "ingest") return t("timeline.ingest");
  if (item.kind === "lane" || item.kind === "research_lane") {
    return t("timeline.lanes");
  }
  if (item.kind === "reconcile") return t("timeline.reconcile");
  if (item.kind === "work") return t("timeline.work");
  if (item.kind === "compose") return t("timeline.compose");
  if (item.kind === "review") return t("timeline.review");
  if (item.kind === "revise") return t("timeline.revise");
  if ("label" in item) return item.label;
  return item.name || item.id;
}

function statusLabel(
  data: CraftJobResponse,
  currentLabel: string,
  t: ReturnType<typeof useTranslations>
): string {
  if (
    data.status === "waiting_specialists" ||
    data.status === "waiting_lanes"
  ) {
    return t("status.waitingLanes");
  }
  if (data.status === "interrupted") return t("status.interrupted");
  if (data.status === "running") {
    return t("status.running", { phase: currentLabel });
  }
  if (data.status === "succeeded") return t("status.succeeded");
  if (data.status === "failed") return t("status.failed");
  return t("status.cancelled");
}

function specialistLabel(
  specialist: CraftJobSpecialistResponse,
  roleT: ReturnType<typeof useTranslations>
): string {
  const role = specialistRoleKey(specialist.role);
  if (role && isKnownSessionRole(role)) {
    return roleT(role);
  }
  return specialist.role;
}

function specialistStatusLabel(
  status: string,
  t: ReturnType<typeof useTranslations>
): string {
  if (status === "running") return t("specialistStatus.running");
  if (status === "succeeded") return t("specialistStatus.succeeded");
  if (status === "failed") return t("specialistStatus.failed");
  return t("specialistStatus.pending");
}

export function CraftJobBannerView({
  data,
  onCancel,
}: {
  data: CraftJobResponse;
  onCancel: () => void;
}) {
  const t = useTranslations("craft.longJob");
  const roleT = useTranslations("craft.projects.detail.sessionRole");
  const timeline = data.timeline ?? [];
  const items = timeline.length > 0 ? timeline : data.phases;
  const current =
    items.find((item) => item.status === "running") ??
    data.phases[data.current_phase_index];
  const currentText = current ? timelineLabel(current, t) : "";
  const failed = data.status === "failed";
  const label = statusLabel(data, currentText, t);
  const errorText = jobErrorDisplay(data.error_detail, t("errorFallback"));
  const specialists = data.specialists ?? [];
  const [open, setOpen] = useState(false);

  const Icon = failed ? SvgAlertTriangle : SvgHourglass;

  return (
    <div className="flex min-w-0 items-center gap-1">
      <Popover open={open} onOpenChange={setOpen}>
        <Popover.Trigger asChild>
          <button
            type="button"
            data-testid="craft-job-banner"
            aria-expanded={open}
            aria-label={open ? t("collapse") : t("expand")}
            className={cn(
              "flex min-w-0 items-center gap-1.5 px-1.5 py-1 rounded-08",
              "transition-colors hover:bg-background-tint-01",
              open && "bg-background-tint-01"
            )}
          >
            <Icon className="h-4 w-4 shrink-0 stroke-text-03" />
            <Text font="main-ui-action" color="text-04" nowrap>
              {t("label")}
            </Text>
            {currentText ? (
              <Text font="secondary-body" color="text-03" nowrap>
                {currentText}
              </Text>
            ) : null}
            <Tag
              title={label}
              color={jobStatusTagColor(data.status)}
              size="sm"
            />
            <SvgChevronDown className="h-4 w-4 shrink-0 stroke-text-03" />
          </button>
        </Popover.Trigger>
        <Popover.Content side="bottom" align="start" width="2xl">
          <div className="flex min-w-0 flex-col gap-2 p-2">
            {(data.name || data.domain) && (
              <div className="flex min-w-0 flex-col gap-1">
                {data.name ? (
                  <Content
                    sizePreset="secondary"
                    variant="section"
                    title={t("goal")}
                    description={data.name}
                    descriptionMaxLines={3}
                  />
                ) : null}
                {data.domain ? (
                  <div className="flex min-w-0 flex-wrap gap-1">
                    <Tag title={t("domain")} value={data.domain} size="sm" />
                  </div>
                ) : null}
              </div>
            )}
            <div
              className="flex min-w-0 flex-wrap gap-1"
              data-testid="craft-job-phases"
            >
              {items.map((item, index) => (
                <span
                  key={`${item.id}-${index}`}
                  data-testid={`craft-job-phase-${item.id}`}
                  data-status={item.status}
                >
                  <Tag
                    title={timelineLabel(item, t)}
                    color={phaseTagColor(item.status)}
                    size="sm"
                  />
                </span>
              ))}
            </div>
            {specialists.length > 0 && (
              <div className="flex min-w-0 flex-col gap-1">
                <Text font="secondary-action" color="text-03">
                  {t("specialists")}
                </Text>
                {specialists.map((specialist) => (
                  <ContentAction
                    key={specialist.id}
                    sizePreset="secondary"
                    variant="section"
                    title={specialistLabel(specialist, roleT)}
                    description={
                      compactJobError(specialist.error_detail, 160) || undefined
                    }
                    rightChildren={
                      <Tag
                        title={specialistStatusLabel(specialist.status, t)}
                        color={phaseTagColor(specialist.status)}
                        size="sm"
                      />
                    }
                  />
                ))}
              </div>
            )}
            {failed && (
              <div
                className="flex min-w-0 flex-col gap-0.5"
                data-testid="craft-job-error"
              >
                <Text font="secondary-action" color="text-03">
                  {t("error")}
                </Text>
                <Text font="secondary-body" color="text-03">
                  {errorText}
                </Text>
              </div>
            )}
          </div>
        </Popover.Content>
      </Popover>
      {isCraftJobInFlight(data) && (
        <Button
          type="button"
          data-testid="craft-job-cancel"
          size="xs"
          prominence="tertiary"
          onClick={onCancel}
        >
          {t("cancel")}
        </Button>
      )}
    </div>
  );
}

export default function CraftJobBanner({
  sessionId,
}: {
  sessionId: string | null;
}) {
  const { data, mutate } = useCraftJob(sessionId);
  if (!data) return null;

  const onCancel = async () => {
    try {
      await cancelCraftJob(data.id);
      void mutate();
    } catch {
      void mutate();
    }
  };

  return <CraftJobBannerView data={data} onCancel={() => void onCancel()} />;
}
