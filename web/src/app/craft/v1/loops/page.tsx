"use client";

import { useCallback, useMemo, useState } from "react";
import useSWR from "swr";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { SettingsLayouts, toast } from "@opal/layouts";
import { Section } from "@/layouts/general-layouts";
import {
  Button,
  Table,
  Text,
  Tooltip,
  createTableColumns,
} from "@opal/components";
import { IllustrationContent } from "@opal/layouts";
import { ConfirmationModalLayout } from "@opal/layouts";
import SvgNoResult from "@opal/illustrations/no-result";
import {
  SvgPauseCircle,
  SvgPlayCircle,
  SvgRefreshCw,
  SvgSimpleLoader,
  SvgTrash,
} from "@opal/icons";
import { deleteLoop, updateLoopState } from "@/app/craft/v1/loops/api";
import { loopDetailPath } from "@/app/craft/v1/loops/constants";
import type { LoopListItem } from "@/app/craft/v1/loops/interfaces";
import {
  LoopHealthBadge,
  LoopStateBadge,
} from "@/app/craft/v1/loops/components/StatusBadge";
import {
  formatAbsolute,
  formatRelativeShort,
} from "@/app/craft/v1/tasks/utils";
import { SWR_KEYS } from "@/lib/swr-keys";
import { errorHandlingFetcher } from "@/lib/fetcher";

const LOOPS_PAGE_SIZE = 20;

const tc = createTableColumns<LoopListItem>();
type LoopsListTranslate = ReturnType<
  typeof useTranslations<"craft.loops.listPage">
>;

function ledgerCounts(loop: LoopListItem): string {
  const parts: string[] = [];
  const queued = loop.counts.queued ?? 0;
  const ready = loop.counts.ready ?? 0;
  const failed = loop.counts.failed ?? 0;
  if (queued) parts.push(`${queued}↗`);
  if (ready) parts.push(`${ready}✓`);
  if (failed) parts.push(`${failed}✕`);
  return parts.length > 0 ? parts.join(" ") : "—";
}

export default function LoopsListPage() {
  const t = useTranslations("craft.loops.listPage");
  const router = useRouter();
  const { data, error, isLoading, mutate } = useSWR<LoopListItem[]>(
    SWR_KEYS.craftLoops,
    errorHandlingFetcher,
    { revalidateOnFocus: false }
  );
  const loops = useMemo(() => data ?? [], [data]);

  const [busyId, setBusyId] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<LoopListItem | null>(null);

  const refresh = useCallback(() => {
    void mutate();
  }, [mutate]);

  const handleToggleState = useCallback(
    async (loop: LoopListItem) => {
      const target = loop.state === "enabled" ? "paused" : "enabled";
      setBusyId(loop.id);
      try {
        await updateLoopState(loop.id, target);
        toast.success(
          target === "enabled"
            ? t("toasts.resumed", { name: loop.name })
            : t("toasts.paused", { name: loop.name })
        );
        refresh();
      } catch (err) {
        toast.error(
          err instanceof Error ? err.message : t("toasts.stateChangeFailed")
        );
      } finally {
        setBusyId(null);
      }
    },
    [refresh, t]
  );

  const handleDelete = useCallback(async () => {
    if (!pendingDelete) return;
    setBusyId(pendingDelete.id);
    try {
      await deleteLoop(pendingDelete.id);
      toast.success(t("toasts.deleted", { name: pendingDelete.name }));
      setPendingDelete(null);
      refresh();
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : t("toasts.deleteFailed")
      );
    } finally {
      setBusyId(null);
    }
  }, [pendingDelete, refresh, t]);

  const columns = useMemo(
    () => [
      tc.column("name", {
        header: t("columns.name"),
        weight: 26,
        enableSorting: false,
        cell: (value) => (
          <Text font="main-ui-body" color="text-05" nowrap>
            {value}
          </Text>
        ),
      }),
      tc.column("trigger_cron", {
        header: t("columns.schedule"),
        weight: 16,
        enableSorting: false,
        cell: (value: string | null) => (
          <Text font="main-ui-body" color="text-03" nowrap>
            {value ?? t("scheduleManual")}
          </Text>
        ),
      }),
      tc.column("state", {
        header: t("columns.state"),
        weight: 11,
        enableSorting: false,
        cell: (state: LoopListItem["state"]) => (
          <LoopStateBadge state={state} />
        ),
      }),
      tc.column("health", {
        header: t("columns.health"),
        weight: 12,
        enableSorting: false,
        cell: (health: LoopListItem["health"]) => (
          <LoopHealthBadge health={health} />
        ),
      }),
      tc.column("counts", {
        header: t("columns.ledger"),
        weight: 12,
        enableSorting: false,
        cell: (_value: Record<string, number>, row: LoopListItem) => (
          <Tooltip
            tooltip={t("ledgerTooltip", {
              queued: row.counts.queued ?? 0,
              ready: row.counts.ready ?? 0,
              failed: row.counts.failed ?? 0,
            })}
            side="top"
          >
            <Text font="main-ui-body" color="text-03" nowrap>
              {ledgerCounts(row)}
            </Text>
          </Tooltip>
        ),
      }),
      tc.column("next_fire_at", {
        header: t("columns.nextFire"),
        weight: 12,
        enableSorting: false,
        cell: (nextFireAt: string | null) => {
          if (!nextFireAt) {
            return (
              <Text font="main-ui-body" color="text-03">
                —
              </Text>
            );
          }
          return (
            <Tooltip tooltip={formatAbsolute(nextFireAt)} side="top">
              <Text font="main-ui-body" color="text-03" nowrap>
                {formatRelativeShort(nextFireAt)}
              </Text>
            </Tooltip>
          );
        },
      }),
      tc.actions({
        showColumnVisibility: false,
        showSorting: false,
        cell: (loop: LoopListItem) => (
          <div className="flex items-center gap-0.5">
            <Tooltip
              tooltip={
                loop.state === "enabled"
                  ? t("rowActions.pauseTooltip")
                  : t("rowActions.resumeTooltip")
              }
              side="top"
            >
              <Button
                icon={loop.state === "enabled" ? SvgPauseCircle : SvgPlayCircle}
                variant="default"
                prominence="tertiary"
                size="sm"
                onClick={() => void handleToggleState(loop)}
                disabled={busyId === loop.id || loop.state === "quarantined"}
                data-testid={`row-toggle-${loop.id}`}
              />
            </Tooltip>
            <Tooltip tooltip={t("rowActions.deleteTooltip")} side="top">
              <Button
                icon={SvgTrash}
                variant="danger"
                prominence="tertiary"
                size="sm"
                onClick={() => setPendingDelete(loop)}
                disabled={busyId === loop.id}
                data-testid={`row-delete-${loop.id}`}
              />
            </Tooltip>
          </div>
        ),
      }),
    ],
    [busyId, handleToggleState, t]
  );

  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header
        icon={SvgRefreshCw}
        title={t("header.title")}
        description={t("header.description")}
      />
      <SettingsLayouts.Body>
        {isLoading ? (
          <div className="flex justify-center py-12">
            <SvgSimpleLoader className="h-6 w-6" />
          </div>
        ) : error ? (
          <Section gap={2}>
            <Text font="main-ui-body" color="text-03">
              {t("errors.loadFailed")}
            </Text>
            <Button
              variant="default"
              prominence="secondary"
              icon={SvgRefreshCw}
              onClick={refresh}
            >
              {t("errors.tryAgainButton")}
            </Button>
          </Section>
        ) : (
          <Table
            data={loops}
            columns={columns}
            getRowId={(row) => row.id}
            pageSize={
              loops.length > 0 ? Math.min(loops.length, LOOPS_PAGE_SIZE) : 1
            }
            selectionBehavior="single-select"
            onRowClick={(row) => router.push(loopDetailPath(row.id))}
            emptyState={
              <IllustrationContent
                illustration={SvgNoResult}
                title={t("empty.title")}
                description={t("empty.description")}
              />
            }
          />
        )}
      </SettingsLayouts.Body>

      {pendingDelete && (
        <ConfirmationModalLayout
          icon={SvgTrash}
          title={t("confirmDelete.title", { name: pendingDelete.name })}
          description={t("confirmDelete.description")}
          onClose={() => setPendingDelete(null)}
          submit={
            <Button
              variant="danger"
              prominence="primary"
              onClick={() => void handleDelete()}
              disabled={busyId === pendingDelete.id}
              data-testid="confirm-delete-loop"
            >
              {busyId === pendingDelete.id
                ? t("confirmDelete.deletingButton")
                : t("confirmDelete.deleteButton")}
            </Button>
          }
        />
      )}
    </SettingsLayouts.Root>
  );
}
