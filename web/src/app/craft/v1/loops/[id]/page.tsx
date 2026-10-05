"use client";

import { useCallback, useMemo, useState } from "react";
import useSWR from "swr";
import { useTranslations } from "next-intl";
import { useParams, useRouter } from "next/navigation";
import { SettingsLayouts, toast } from "@opal/layouts";
import {
  Button,
  Switch,
  Table,
  Text,
  Tooltip,
  createTableColumns,
} from "@opal/components";
import { ConfirmationModalLayout } from "@opal/layouts";
import {
  SvgArrowLeft,
  SvgCheckCircle,
  SvgPauseCircle,
  SvgPlayCircle,
  SvgRefreshCw,
  SvgSimpleLoader,
  SvgTrash,
} from "@opal/icons";
import {
  deleteLoop,
  decideLoopOutput,
  retryLoopItem,
  setLoopAutopilot,
  updateLoopState,
} from "@/app/craft/v1/loops/api";
import { LOOPS_PATH } from "@/app/craft/v1/loops/constants";
import type {
  LoopGrant,
  LoopItem,
  LoopListItem,
  LoopOutput,
} from "@/app/craft/v1/loops/interfaces";
import {
  LoopItemStatusBadge,
  LoopOutputStateBadge,
  LoopStateBadge,
  LoopHealthBadge,
} from "@/app/craft/v1/loops/components/StatusBadge";
import ReturnModal from "@/app/craft/v1/loops/components/ReturnModal";
import GrantModal from "@/app/craft/v1/loops/components/GrantModal";
import { formatRelativeShort } from "@/app/craft/v1/tasks/utils";
import { SWR_KEYS } from "@/lib/swr-keys";
import { errorHandlingFetcher } from "@/lib/fetcher";

const DETAIL_PAGE_SIZE = 10;

export default function LoopDetailPage() {
  const t = useTranslations("craft.loops.detailPage");
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const loopId = params?.id;

  const {
    data: loop,
    error,
    isLoading,
    mutate,
  } = useSWR<LoopListItem>(
    loopId ? SWR_KEYS.craftLoop(loopId) : null,
    errorHandlingFetcher,
    { revalidateOnFocus: false }
  );
  const { data: items, mutate: mutateItems } = useSWR<LoopItem[]>(
    loopId ? SWR_KEYS.craftLoopItems(loopId) : null,
    errorHandlingFetcher,
    { revalidateOnFocus: false }
  );
  const { data: outputs, mutate: mutateOutputs } = useSWR<LoopOutput[]>(
    loopId ? SWR_KEYS.craftLoopOutputs(loopId) : null,
    errorHandlingFetcher,
    { revalidateOnFocus: false }
  );
  const { data: grants, mutate: mutateGrants } = useSWR<LoopGrant[]>(
    loopId ? SWR_KEYS.craftLoopGrants(loopId) : null,
    errorHandlingFetcher,
    { revalidateOnFocus: false }
  );

  const [busy, setBusy] = useState(false);
  const [pendingDelete, setPendingDelete] = useState(false);
  const [pendingReturn, setPendingReturn] = useState<LoopOutput | null>(null);
  const [grantOpen, setGrantOpen] = useState(false);

  const refreshAll = useCallback(() => {
    void mutate();
    void mutateItems();
    void mutateOutputs();
    void mutateGrants();
  }, [mutate, mutateItems, mutateOutputs, mutateGrants]);

  const handleToggleState = useCallback(async () => {
    if (!loop) return;
    const target = loop.state === "enabled" ? "paused" : "enabled";
    setBusy(true);
    try {
      await updateLoopState(loop.id, target);
      refreshAll();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("toasts.failed"));
    } finally {
      setBusy(false);
    }
  }, [loop, refreshAll, t]);

  const handleAutopilot = useCallback(
    async (enabled: boolean) => {
      if (!loop) return;
      setBusy(true);
      try {
        await setLoopAutopilot(loop.id, enabled);
        toast.success(
          enabled ? t("toasts.autopilotOn") : t("toasts.autopilotOff")
        );
        refreshAll();
      } catch (err) {
        toast.error(err instanceof Error ? err.message : t("toasts.failed"));
        // Revert optimistic switch state by revalidating.
        refreshAll();
      } finally {
        setBusy(false);
      }
    },
    [loop, refreshAll, t]
  );

  const handleShip = useCallback(
    async (output: LoopOutput) => {
      if (!loopId) return;
      setBusy(true);
      try {
        await decideLoopOutput(loopId, output.id, "ship");
        toast.success(t("toasts.shipped", { title: output.title }));
        refreshAll();
      } catch (err) {
        toast.error(err instanceof Error ? err.message : t("toasts.failed"));
      } finally {
        setBusy(false);
      }
    },
    [loopId, refreshAll, t]
  );

  const handleRetry = useCallback(
    async (item: LoopItem) => {
      if (!loopId) return;
      setBusy(true);
      try {
        await retryLoopItem(loopId, item.id);
        toast.success(t("toasts.retried", { key: item.source_key }));
        refreshAll();
      } catch (err) {
        toast.error(err instanceof Error ? err.message : t("toasts.failed"));
      } finally {
        setBusy(false);
      }
    },
    [loopId, refreshAll, t]
  );

  const handleDelete = useCallback(async () => {
    if (!loop) return;
    setBusy(true);
    try {
      await deleteLoop(loop.id);
      router.push(LOOPS_PATH);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("toasts.failed"));
      setBusy(false);
    }
  }, [loop, router, t]);

  const outputColumns = useMemo(
    () =>
      buildOutputColumns(t, {
        busy,
        onShip: (output) => void handleShip(output),
        onReturn: (output) => setPendingReturn(output),
      }),
    [t, busy, handleShip]
  );
  const itemColumns = useMemo(
    () =>
      buildItemColumns(t, {
        busy,
        onRetry: (item) => void handleRetry(item),
      }),
    [t, busy, handleRetry]
  );

  if (isLoading) {
    return (
      <div className="flex justify-center py-12">
        <SvgSimpleLoader className="h-6 w-6" />
      </div>
    );
  }
  if (error || !loop) {
    return (
      <SettingsLayouts.Root width="lg">
        <SettingsLayouts.Header
          icon={SvgRefreshCw}
          title={t("fallbackTitle")}
          backButton={() => router.push(LOOPS_PATH)}
        />
        <SettingsLayouts.Body>
          <Text font="main-ui-body" color="text-03">
            {t("errors.loadFailed")}
          </Text>
        </SettingsLayouts.Body>
      </SettingsLayouts.Root>
    );
  }

  // Autopilot is derived: every declared gate flipped to "auto" by the
  // backend's set_autopilot; an empty action list is never autopilot.
  const autopilotEnabled =
    loop.ship_actions.length > 0 &&
    loop.ship_actions.every((spec) => spec.gate === "auto");

  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header
        icon={SvgRefreshCw}
        title={loop.name}
        description={t("header.description", {
          cron: loop.trigger_cron ?? t("scheduleManual"),
          version: loop.policy_version,
        })}
        backButton={() => router.push(LOOPS_PATH)}
        rightChildren={
          <div className="flex items-center gap-3">
            <label
              className="flex cursor-pointer items-center gap-2"
              htmlFor="loop-autopilot"
              data-testid="loop-autopilot-row"
            >
              <Text font="main-ui-body" color="text-03">
                {t("autopilot.label")}
              </Text>
              <Switch
                id="loop-autopilot"
                checked={autopilotEnabled}
                onCheckedChange={(checked) => void handleAutopilot(checked)}
                disabled={busy}
                data-testid="loop-autopilot-switch"
              />
            </label>
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
                prominence="secondary"
                onClick={() => void handleToggleState()}
                disabled={busy || loop.state === "quarantined"}
                data-testid="loop-toggle-state"
              />
            </Tooltip>
            <Tooltip tooltip={t("rowActions.deleteTooltip")} side="top">
              <Button
                icon={SvgTrash}
                variant="danger"
                prominence="secondary"
                onClick={() => setPendingDelete(true)}
                disabled={busy}
                data-testid="loop-delete"
              />
            </Tooltip>
          </div>
        }
      />
      <SettingsLayouts.Body>
        <div className="mb-3 flex items-center gap-2">
          <LoopStateBadge state={loop.state} />
          <LoopHealthBadge health={loop.health} />
          {loop.consecutive_failed_fires > 0 && (
            <Text font="figure-small-label" color="text-03">
              {t("failedFires", { count: loop.consecutive_failed_fires })}
            </Text>
          )}
        </div>

        <div className="mb-2">
          <Text font="heading-h3">{t("outputs.title")}</Text>
        </div>
        <Table
          data={outputs ?? []}
          columns={outputColumns}
          getRowId={(row) => row.id}
          pageSize={
            (outputs?.length ?? 0) > 0
              ? Math.min(outputs!.length, DETAIL_PAGE_SIZE)
              : 1
          }
          emptyState={<Text color="text-03">{t("outputs.empty")}</Text>}
        />

        <div className="mb-2 mt-6">
          <Text font="heading-h3">{t("ledger.title")}</Text>
        </div>
        <Table
          data={items ?? []}
          columns={itemColumns}
          getRowId={(row) => row.id}
          pageSize={
            (items?.length ?? 0) > 0
              ? Math.min(items!.length, DETAIL_PAGE_SIZE)
              : 1
          }
          emptyState={<Text color="text-03">{t("ledger.empty")}</Text>}
        />

        <div className="mb-2 mt-6 flex items-center justify-between">
          <Text font="heading-h3">{t("grants.title")}</Text>
          <Button
            variant="default"
            prominence="secondary"
            size="sm"
            icon={SvgCheckCircle}
            onClick={() => setGrantOpen(true)}
            data-testid="open-grant-modal"
          >
            {t("grants.grantButton")}
          </Button>
        </div>
        <GrantTable grants={grants ?? []} t={t} />
      </SettingsLayouts.Body>

      {pendingDelete && (
        <ConfirmationModalLayout
          icon={SvgTrash}
          title={t("confirmDelete.title", { name: loop.name })}
          description={t("confirmDelete.description")}
          onClose={() => setPendingDelete(false)}
          submit={
            <Button
              variant="danger"
              prominence="primary"
              onClick={() => void handleDelete()}
              disabled={busy}
              data-testid="confirm-delete-loop"
            >
              {t("confirmDelete.deleteButton")}
            </Button>
          }
        />
      )}

      {loopId && (
        <>
          <ReturnModal
            loopId={loopId}
            output={pendingReturn}
            onClose={() => setPendingReturn(null)}
            onDecided={refreshAll}
          />
          <GrantModal
            loopId={loopId}
            shipActions={loop.ship_actions}
            open={grantOpen}
            onClose={() => setGrantOpen(false)}
            onGranted={refreshAll}
          />
        </>
      )}
    </SettingsLayouts.Root>
  );
}

// ---------------------------------------------------------------------------
// Tables
// ---------------------------------------------------------------------------

type DetailTranslate = ReturnType<
  typeof useTranslations<"craft.loops.detailPage">
>;

function buildOutputColumns(
  t: DetailTranslate,
  handlers: {
    busy: boolean;
    onShip: (output: LoopOutput) => void;
    onReturn: (output: LoopOutput) => void;
  }
) {
  const tc = createTableColumns<LoopOutput>();
  return [
    tc.column("title", {
      header: t("outputs.columns.title"),
      weight: 30,
      enableSorting: false,
      cell: (value: string, row) => (
        <div className="flex flex-col">
          <Text font="main-ui-body" color="text-05" nowrap>
            {value}
          </Text>
          {row.summary && (
            <Text font="secondary-body" color="text-03" nowrap>
              {row.summary.slice(0, 120)}
            </Text>
          )}
        </div>
      ),
    }),
    tc.column("ship_action", {
      header: t("outputs.columns.action"),
      weight: 16,
      enableSorting: false,
      cell: (value: string) => (
        <Text font="main-ui-body" color="text-03" nowrap>
          {value}
        </Text>
      ),
    }),
    tc.column("state", {
      header: t("outputs.columns.state"),
      weight: 16,
      enableSorting: false,
      cell: (state: LoopOutput["state"]) => (
        <LoopOutputStateBadge state={state} />
      ),
    }),
    tc.column("decided_at", {
      header: t("outputs.columns.decided"),
      weight: 18,
      enableSorting: false,
      cell: (decidedAt: string | null) =>
        decidedAt ? (
          <Text font="main-ui-body" color="text-03" nowrap>
            {formatRelativeShort(decidedAt)}
          </Text>
        ) : (
          <Text font="main-ui-body" color="text-03">
            —
          </Text>
        ),
    }),
    tc.actions({
      showColumnVisibility: false,
      showSorting: false,
      cell: (output: LoopOutput) =>
        output.state === "ready" ? (
          <div className="flex items-center gap-0.5">
            <Tooltip tooltip={t("outputs.shipTooltip")} side="top">
              <Button
                icon={SvgCheckCircle}
                variant="default"
                prominence="tertiary"
                size="sm"
                onClick={() => handlers.onShip(output)}
                disabled={handlers.busy}
                data-testid={`ship-output-${output.id}`}
              />
            </Tooltip>
            <Tooltip tooltip={t("outputs.returnTooltip")} side="top">
              <Button
                icon={SvgArrowLeft}
                variant="default"
                prominence="tertiary"
                size="sm"
                onClick={() => handlers.onReturn(output)}
                disabled={handlers.busy}
                data-testid={`return-output-${output.id}`}
              />
            </Tooltip>
          </div>
        ) : null,
    }),
  ];
}

function buildItemColumns(
  t: DetailTranslate,
  handlers: { busy: boolean; onRetry: (item: LoopItem) => void }
) {
  const tc = createTableColumns<LoopItem>();
  return [
    tc.column("source_key", {
      header: t("ledger.columns.key"),
      weight: 26,
      enableSorting: false,
      cell: (value: string, row) => (
        <div className="flex flex-col">
          <Text font="main-ui-body" color="text-05" nowrap>
            {value}
          </Text>
          {row.source_summary && (
            <Text font="secondary-body" color="text-03" nowrap>
              {row.source_summary.slice(0, 120)}
            </Text>
          )}
        </div>
      ),
    }),
    tc.column("status", {
      header: t("ledger.columns.status"),
      weight: 14,
      enableSorting: false,
      cell: (status: LoopItem["status"]) => (
        <LoopItemStatusBadge status={status} />
      ),
    }),
    tc.column("attempts", {
      header: t("ledger.columns.attempts"),
      weight: 10,
      enableSorting: false,
      cell: (value: number) => (
        <Text font="main-ui-body" color="text-03">
          {String(value)}
        </Text>
      ),
    }),
    tc.column("guidance", {
      header: t("ledger.columns.guidance"),
      weight: 30,
      enableSorting: false,
      cell: (guidance: string | null) =>
        guidance ? (
          <Tooltip tooltip={guidance} side="top">
            <Text font="main-ui-body" color="text-03" nowrap>
              {guidance.slice(0, 80)}
            </Text>
          </Tooltip>
        ) : (
          <Text font="main-ui-body" color="text-03">
            —
          </Text>
        ),
    }),
    tc.actions({
      showColumnVisibility: false,
      showSorting: false,
      cell: (item: LoopItem) =>
        item.status === "failed" ? (
          <Tooltip tooltip={t("ledger.retryTooltip")} side="top">
            <Button
              icon={SvgRefreshCw}
              variant="default"
              prominence="tertiary"
              size="sm"
              onClick={() => handlers.onRetry(item)}
              disabled={handlers.busy}
              data-testid={`retry-item-${item.id}`}
            />
          </Tooltip>
        ) : null,
    }),
  ];
}

function GrantTable({
  grants,
  t,
}: {
  grants: LoopGrant[];
  t: DetailTranslate;
}) {
  const tc = createTableColumns<LoopGrant>();
  const columns = [
    tc.column("ship_action", {
      header: t("grants.columns.action"),
      weight: 24,
      enableSorting: false,
      cell: (value: string) => (
        <Text font="main-ui-body" color="text-05" nowrap>
          {value}
        </Text>
      ),
    }),
    tc.column("label", {
      header: t("grants.columns.label"),
      weight: 22,
      enableSorting: false,
      cell: (value: string | null) => (
        <Text font="main-ui-body" color="text-03" nowrap>
          {value ?? "—"}
        </Text>
      ),
    }),
    tc.column("policy_version", {
      header: t("grants.columns.policyVersion"),
      weight: 16,
      enableSorting: false,
      cell: (value: number) => (
        <Text font="main-ui-body" color="text-03">
          {String(value)}
        </Text>
      ),
    }),
    tc.column("created_at", {
      header: t("grants.columns.created"),
      weight: 18,
      enableSorting: false,
      cell: (value: string) => (
        <Text font="main-ui-body" color="text-03" nowrap>
          {formatRelativeShort(value)}
        </Text>
      ),
    }),
    tc.column("revoked_at", {
      header: t("grants.columns.status"),
      weight: 12,
      enableSorting: false,
      cell: (revokedAt: string | null) =>
        revokedAt ? (
          <Text font="main-ui-body" color="text-03">
            {t("grants.revoked")}
          </Text>
        ) : (
          <Text font="main-ui-body" color="status-success-05">
            {t("grants.active")}
          </Text>
        ),
    }),
  ];
  return (
    <Table
      data={grants}
      columns={columns}
      getRowId={(row) => row.id}
      pageSize={
        grants.length > 0 ? Math.min(grants.length, DETAIL_PAGE_SIZE) : 1
      }
      emptyState={<Text color="text-03">{t("grants.empty")}</Text>}
    />
  );
}
