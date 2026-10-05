"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import useSWR from "swr";
import { useTranslations } from "next-intl";
import {
  Button,
  Card,
  MessageCard,
  Table,
  Tag,
  Text,
  Tooltip,
  createTableColumns,
} from "@opal/components";
import {
  Content,
  ContentAction,
  IllustrationContent,
  SettingsLayouts,
  toast,
} from "@opal/layouts";
import { SvgPlayCircle, SvgRefreshCw, SvgSimpleLoader } from "@opal/icons";
import SvgNoResult from "@opal/illustrations/no-result";
import { timeAgo } from "@opal/time";
import { ADMIN_ROUTES } from "@/lib/admin-routes";
import { SWR_KEYS } from "@/lib/swr-keys";
import {
  getCraftEvalRun,
  listCraftEvalCases,
  listCraftEvalRuns,
  triggerCraftEvalRun,
} from "@/lib/craft-evals/api";
import {
  isRunTerminal,
  readRegressions,
  type CraftEvalCaseSummary,
  type CraftEvalRunSummary,
} from "@/lib/craft-evals/types";
import CaseResultCard from "./CaseResultCard";
import EvalStatusBadge from "./EvalStatusBadge";
import {
  formatDateTime,
  formatDuration,
  formatScore,
  getTriggerKey,
  getTriggerTagColor,
} from "./utils";

const RUNS_LIMIT = 20;
const POLL_INTERVAL_MS = 15_000;
const CASES_PAGE_SIZE = 12;

const runTc = createTableColumns<CraftEvalRunSummary>();
const caseTc = createTableColumns<CraftEvalCaseSummary>();

// ---------------------------------------------------------------------------
// Latest-run summary strip
// ---------------------------------------------------------------------------

function SummaryStat({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="flex w-full flex-col items-start gap-0.5 rounded-08 p-2">
      {children}
      <Text font="secondary-body" color="text-03">
        {label}
      </Text>
    </div>
  );
}

function LatestRunSummary({ run }: { run: CraftEvalRunSummary }) {
  const t = useTranslations("admin.craft.evaluations");

  return (
    <Card border="solid" padding={2} rounding={4}>
      <div className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4">
        <SummaryStat label={t("summary.status")}>
          <EvalStatusBadge status={run.status} />
        </SummaryStat>
        <SummaryStat label={t("summary.score")}>
          <Text font="main-ui-action" color="text-04">
            {formatScore(run.score)}
          </Text>
        </SummaryStat>
        <SummaryStat label={t("summary.passed")}>
          <Text font="main-ui-action" color="text-04">
            {`${run.passed_count}/${run.case_count}`}
          </Text>
        </SummaryStat>
        <SummaryStat label={t("summary.lastRun")}>
          <Text font="main-ui-action" color="text-04">
            {timeAgo(run.created_at) ?? "–"}
          </Text>
        </SummaryStat>
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Section loading placeholder
// ---------------------------------------------------------------------------

function SectionLoader() {
  return (
    <div className="flex justify-center py-12">
      <SvgSimpleLoader className="h-6 w-6" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function CraftEvaluationsPage() {
  const t = useTranslations("admin.craft.evaluations");
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [isTriggering, setIsTriggering] = useState(false);

  const {
    data: cases,
    isLoading: casesLoading,
    error: casesError,
    mutate: mutateCases,
  } = useSWR(SWR_KEYS.craftEvalCases, () => listCraftEvalCases(), {
    revalidateOnFocus: false,
  });

  const {
    data: runs,
    isLoading: runsLoading,
    error: runsError,
    mutate: mutateRuns,
  } = useSWR(
    SWR_KEYS.craftEvalRuns(RUNS_LIMIT),
    () => listCraftEvalRuns(RUNS_LIMIT),
    {
      // Poll only while a run is in flight.
      refreshInterval: (latest) =>
        latest?.some((run) => !isRunTerminal(run.status))
          ? POLL_INTERVAL_MS
          : 0,
      revalidateOnFocus: false,
    }
  );

  const {
    data: detail,
    isLoading: detailLoading,
    error: detailError,
    mutate: mutateDetail,
  } = useSWR(
    selectedRunId ? SWR_KEYS.craftEvalRunDetail(selectedRunId) : null,
    () => {
      if (selectedRunId === null) {
        return Promise.reject(new Error("No eval run selected"));
      }
      return getCraftEvalRun(selectedRunId);
    },
    {
      refreshInterval: (latest) =>
        latest && !isRunTerminal(latest.status) ? POLL_INTERVAL_MS : 0,
      revalidateOnFocus: false,
    }
  );

  // Auto-select the newest run until the admin picks one.
  const latestRun = runs?.[0];
  useEffect(() => {
    if (latestRun && selectedRunId === null) {
      setSelectedRunId(latestRun.id);
    }
  }, [latestRun, selectedRunId]);

  const loadError = casesError ?? runsError ?? detailError;
  const loadErrorMessage = loadError
    ? loadError instanceof Error
      ? loadError.message
      : String(loadError)
    : null;

  const handleRefresh = useCallback(() => {
    void mutateCases();
    void mutateRuns();
    void mutateDetail();
  }, [mutateCases, mutateRuns, mutateDetail]);

  const handleTrigger = useCallback(
    async (caseSlugs: string[] | null) => {
      setIsTriggering(true);
      try {
        const created = await triggerCraftEvalRun(caseSlugs);
        toast.success(t("toasts.triggered"));
        setSelectedRunId(created.id);
        await mutateRuns();
      } catch (error) {
        toast.error(
          error instanceof Error && error.message
            ? error.message
            : t("toasts.triggerFailed")
        );
      } finally {
        setIsTriggering(false);
      }
    },
    [mutateRuns, t]
  );

  const runColumns = useMemo(
    () => [
      runTc.column("created_at", {
        header: t("runs.created"),
        weight: 16,
        enableSorting: false,
        cell: (value) => (
          <Tooltip tooltip={formatDateTime(String(value ?? ""))}>
            <Text font="secondary-body" color="text-03" nowrap>
              {timeAgo(String(value ?? "")) ?? "–"}
            </Text>
          </Tooltip>
        ),
      }),
      runTc.column("trigger", {
        header: t("runs.trigger"),
        weight: 10,
        enableSorting: false,
        cell: (value) => (
          <Tag
            title={t(`runs.triggerValue.${getTriggerKey(String(value))}`)}
            color={getTriggerTagColor(String(value))}
          />
        ),
      }),
      runTc.column("status", {
        header: t("runs.status"),
        weight: 12,
        enableSorting: false,
        cell: (value) => <EvalStatusBadge status={String(value)} />,
      }),
      runTc.column("score", {
        header: t("runs.score"),
        weight: 8,
        enableSorting: false,
        cell: (value) => (
          <Text font="main-ui-action" color="text-05">
            {formatScore(value === null ? null : Number(value))}
          </Text>
        ),
      }),
      runTc.column("passed_count", {
        header: t("runs.cases"),
        weight: 8,
        enableSorting: false,
        cell: (value, row) => (
          <Text font="secondary-body" color="text-03" nowrap>
            {`${String(value)}/${String(row.case_count)}`}
          </Text>
        ),
      }),
      runTc.column("model_name", {
        header: t("runs.model"),
        weight: 16,
        enableSorting: false,
        cell: (value, row) => (
          <Text font="secondary-body" color="text-03" wordWrap="wrap-anywhere">
            {`${row.model_provider ? `${row.model_provider} / ` : ""}${value ?? "–"}`}
          </Text>
        ),
      }),
    ],
    [t]
  );

  const caseColumns = useMemo(
    () => [
      caseTc.column("name", {
        header: t("cases.name"),
        weight: 24,
        enableSorting: false,
        cell: (value) => (
          <Text font="main-ui-body" color="text-05">
            {String(value)}
          </Text>
        ),
      }),
      caseTc.column("domain", {
        header: t("cases.domain"),
        weight: 12,
        enableSorting: false,
        cell: (value) => <Tag title={String(value)} color="gray" />,
      }),
      caseTc.column("value_anchor_count", {
        header: t("cases.anchors"),
        weight: 8,
        enableSorting: false,
        cell: (value) => (
          <Text font="secondary-body" color="text-03">
            {String(value ?? 0)}
          </Text>
        ),
      }),
      caseTc.column("rubric_criterion_count", {
        header: t("cases.rubric"),
        weight: 8,
        enableSorting: false,
        cell: (value) => (
          <Text font="secondary-body" color="text-03">
            {String(value ?? 0)}
          </Text>
        ),
      }),
      caseTc.column("budget_seconds", {
        header: t("cases.budget"),
        weight: 10,
        enableSorting: false,
        cell: (value) => (
          <Text font="secondary-body" color="text-03">
            {formatDuration(Number(value ?? 0))}
          </Text>
        ),
      }),
      caseTc.actions({
        showColumnVisibility: false,
        showSorting: false,
        cell: (row) => (
          <Button
            prominence="internal"
            size="sm"
            icon={SvgPlayCircle}
            disabled={isTriggering}
            tooltip={t("cases.runCase")}
            onClick={() => void handleTrigger([row.slug])}
          >
            {t("cases.runCase")}
          </Button>
        ),
      }),
    ],
    [t, handleTrigger, isTriggering]
  );

  const regressions = useMemo(
    () => (detail ? readRegressions(detail.summary) : []),
    [detail]
  );

  return (
    <SettingsLayouts.Root width="lg">
      <SettingsLayouts.Header
        icon={ADMIN_ROUTES.CRAFT_EVALUATIONS.icon}
        title={t("title")}
        description={t("description")}
        divider
        rightChildren={
          <div className="flex items-center gap-2">
            <Button
              prominence="secondary"
              icon={SvgRefreshCw}
              onClick={handleRefresh}
              data-testid="eval-refresh"
            >
              {t("refresh")}
            </Button>
            <Button
              icon={SvgPlayCircle}
              disabled={isTriggering || !cases || cases.length === 0}
              onClick={() => void handleTrigger(null)}
              data-testid="eval-run-all"
            >
              {isTriggering ? t("toasts.triggering") : t("runAll")}
            </Button>
          </div>
        }
      >
        {/* Only block the page when the initial load failed; a background
            revalidation error keeps the already-rendered data usable. */}
        {loadErrorMessage && !cases && !runs && (
          <MessageCard
            variant="error"
            title={t("toasts.loadFailed")}
            description={loadErrorMessage}
          />
        )}
      </SettingsLayouts.Header>

      <SettingsLayouts.Body>
        {latestRun && <LatestRunSummary run={latestRun} />}

        <div className="flex flex-col gap-3">
          <Content
            sizePreset="main-content"
            variant="section"
            title={t("runs.title")}
          />
          {runsLoading ? (
            <SectionLoader />
          ) : (
            <Table
              data={runs ?? []}
              columns={runColumns}
              getRowId={(row) => row.id}
              pageSize={RUNS_LIMIT}
              variant="cards"
              onRowClick={(row) => setSelectedRunId(row.id)}
              getRowLabel={(row) =>
                `${t("detail.title")} ${formatDateTime(row.created_at)}`
              }
              emptyState={
                <IllustrationContent
                  illustration={SvgNoResult}
                  title={t("runs.emptyTitle")}
                  description={t("runs.emptyDescription")}
                />
              }
            />
          )}
        </div>

        {detailLoading && !detail && selectedRunId ? <SectionLoader /> : null}

        {detail && (
          <div className="flex flex-col gap-3" data-testid="eval-run-detail">
            <ContentAction
              sizePreset="main-content"
              variant="section"
              title={`${t("detail.title")} · ${detail.id.slice(0, 8)}`}
              padding={0}
              rightChildren={
                <div className="flex flex-wrap items-center gap-3">
                  <EvalStatusBadge status={detail.status} />
                  <Text font="main-ui-action" color="text-05">
                    {formatScore(detail.score)}
                  </Text>
                  <Text font="secondary-body" color="text-03" nowrap>
                    {`${detail.passed_count}/${detail.case_count} ${t("detail.passed")}`}
                  </Text>
                </div>
              }
            />

            {detail.error_detail && (
              <MessageCard
                variant="error"
                title={t("detail.error")}
                description={detail.error_detail}
              />
            )}

            {regressions.length > 0 && (
              <MessageCard
                variant="warning"
                title={t("detail.regressions")}
                bottomChildren={
                  <ul className="flex flex-col gap-1">
                    {regressions.map((item) => (
                      <li key={item.case} className="flex items-baseline gap-2">
                        <Text
                          font="secondary-mono"
                          color="text-05"
                          wordWrap="wrap-anywhere"
                        >
                          {item.case}
                        </Text>
                        <Text font="secondary-body" color="text-03">
                          {`${formatScore(item.previous_score)} → ${formatScore(item.score)}`}
                        </Text>
                      </li>
                    ))}
                  </ul>
                }
              />
            )}

            <div className="flex flex-col gap-3">
              {detail.case_results.map((result) => (
                <CaseResultCard key={result.case_slug} result={result} />
              ))}
            </div>
          </div>
        )}

        <div className="flex flex-col gap-3">
          <Content
            sizePreset="main-content"
            variant="section"
            title={t("cases.title")}
          />
          {casesLoading ? (
            <SectionLoader />
          ) : (
            <Table
              data={cases ?? []}
              columns={caseColumns}
              getRowId={(row) => row.slug}
              pageSize={CASES_PAGE_SIZE}
              variant="cards"
              emptyState={
                <IllustrationContent
                  illustration={SvgNoResult}
                  title={t("cases.emptyTitle")}
                  description={t("cases.emptyDescription")}
                />
              }
            />
          )}
        </div>
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
