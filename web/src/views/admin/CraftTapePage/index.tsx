"use client";

/**
 * Admin execution-tape entry (/admin/craft/tapes): the tenant-wide stats
 * strip (tiles, outcome/runtime breakdowns, daily series chart) above the
 * same dsh-style master-detail browser as the personal entry, reading the
 * FULL_ADMIN_PANEL_ACCESS-scoped /api/build/admin/tape base.
 */

import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import {
  Bar,
  BarChart,
  ResponsiveContainer,
  Tooltip as ChartTooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card, Tag } from "@opal/components";
import { SettingsLayouts, toast } from "@opal/layouts";
import { ADMIN_ROUTES } from "@/lib/admin-routes";
import TapeListBrowser from "@/components/craft-tape/TapeListBrowser";
import TapeNoSelection from "@/components/craft-tape/TapeNoSelection";
import ReasonTag from "@/components/craft-tape/ReasonTag";
import TapeSessionDetail from "@/components/craft-tape/TapeSessionDetail";
import { useTapeSelection } from "@/components/craft-tape/useTapeSelection";
import { isoDaysAgo } from "@/components/craft-tape/constants";
import { fetchTapeStats, fetchTapeStatsSeries } from "@/lib/craft-tape/api";
import type {
  TapeSessionItem,
  TapeStats,
  TapeStatsSeriesPoint,
} from "@/lib/craft-tape/types";
import { errorMessage } from "@/views/admin/McpGatewayPage/format";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/sections/extend/ui/resizable";

const ROUTE = ADMIN_ROUTES.CRAFT_TAPE;

const WINDOW_OPTIONS = [7, 30, 90] as const;

export default function CraftTapePage() {
  const t = useTranslations("admin.craftTape");
  const { selectedId, select } = useTapeSelection();
  const [knownSessions, setKnownSessions] = useState<
    Map<string, TapeSessionItem>
  >(new Map());
  const [days, setDays] = useState<number>(30);
  const [stats, setStats] = useState<TapeStats | null>(null);
  const [series, setSeries] = useState<TapeStatsSeriesPoint[]>([]);

  useEffect(() => {
    const window = {
      from: isoDaysAgo(days),
      to: new Date().toISOString(),
    };
    fetchTapeStats(window)
      .then(setStats)
      .catch((error) => toast.error(errorMessage(error, t("loadFailed"))));
    fetchTapeStatsSeries(window)
      .then((result) => setSeries(result.series))
      .catch(() => setSeries([]));
  }, [days, t]);

  const onItemsKnown = useMemo(
    () => (items: TapeSessionItem[]) => {
      setKnownSessions((current) => {
        const next = new Map(current);
        for (const item of items) next.set(item.session_id, item);
        return next.size === current.size ? current : next;
      });
    },
    []
  );

  const selected = selectedId ? (knownSessions.get(selectedId) ?? null) : null;

  return (
    <SettingsLayouts.Root width="full">
      <SettingsLayouts.Header
        icon={ROUTE.icon}
        title={t("page.title")}
        description={t("page.description")}
        divider
      />
      <SettingsLayouts.Body>
        <div className="flex flex-col gap-4" data-testid="craft-tape-page">
          {!stats?.archiving_enabled ? (
            <Card padding={3} rounding={3}>
              <div className="flex items-center gap-2">
                <Tag title={t("overview.disabled")} color="amber" />
                <span className="text-sm text-neutral-500">
                  {t("overview.disabledHint")}
                </span>
              </div>
            </Card>
          ) : (
            <StatsOverview
              stats={stats}
              series={series}
              days={days}
              onDays={setDays}
            />
          )}

          <div className="flex h-[calc(100dvh-32rem)] min-h-[26rem]">
            <ResizablePanelGroup orientation="horizontal">
              <ResizablePanel defaultSize="30" minSize="20" className="h-full">
                <TapeListBrowser
                  variant="admin"
                  selectedId={selectedId}
                  onSelect={(session) => select(session.session_id)}
                  onItemsKnown={onItemsKnown}
                />
              </ResizablePanel>
              <ResizableHandle />
              <ResizablePanel defaultSize="70" className="h-full">
                {selectedId ? (
                  <div className="h-full overflow-y-auto pl-4 pr-1">
                    <TapeSessionDetail
                      key={selectedId}
                      sessionId={selectedId}
                      session={selected}
                      variant="admin"
                      onClose={() => select(null)}
                    />
                  </div>
                ) : (
                  <TapeNoSelection />
                )}
              </ResizablePanel>
            </ResizablePanelGroup>
          </div>
        </div>
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}

// ---------------------------------------------------------------------------
// Stats overview strip
// ---------------------------------------------------------------------------

function StatsOverview({
  stats,
  series,
  days,
  onDays,
}: {
  stats: TapeStats;
  series: TapeStatsSeriesPoint[];
  days: number;
  onDays: (days: number) => void;
}) {
  const t = useTranslations("admin.craftTape");
  const reasons = Object.entries(stats.by_reason).sort(([, a], [, b]) => b - a);
  const runtimes = Object.entries(stats.by_runtime).sort(
    ([, a], [, b]) => b - a
  );

  return (
    <Card padding={3} rounding={3}>
      <div className="flex flex-col gap-3">
        {/* Tiles + window selector */}
        <div className="flex flex-wrap items-end gap-6">
          <StatTile
            label={t("overview.sessions")}
            value={String(stats.sessions)}
          />
          <StatTile label={t("overview.turns")} value={String(stats.turns)} />
          <StatTile label={t("overview.events")} value={String(stats.events)} />
          <StatTile
            label={t("overview.outputTokens")}
            value={stats.output_tokens.toLocaleString()}
          />
          <StatTile
            label={t("overview.cost")}
            value={`$${stats.cost.toFixed(2)}`}
          />
          <div
            className="ml-auto flex items-center gap-1"
            data-testid="craft-tape-window"
          >
            {WINDOW_OPTIONS.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => onDays(option)}
                className={`rounded-md px-2 py-1 text-xs ${
                  days === option
                    ? "bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900"
                    : "text-neutral-500 hover:bg-neutral-100 dark:text-neutral-400 dark:hover:bg-neutral-800"
                }`}
                data-testid={`craft-tape-window-${option}`}
              >
                {t("filters.days", { days: option })}
              </button>
            ))}
          </div>
        </div>

        {/* Breakdown chips */}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
          {reasons.map(([reason, count]) => (
            <span key={reason} className="flex items-center gap-1.5 text-xs">
              <ReasonTag reason={reason} />
              <span className="text-neutral-500">{count}</span>
            </span>
          ))}
          {runtimes.map(([runtime, count]) => (
            <span
              key={runtime}
              className="flex items-center gap-1 font-mono text-xs text-neutral-500 dark:text-neutral-400"
            >
              {runtime}
              <span className="text-neutral-400 dark:text-neutral-500">
                ×{count}
              </span>
            </span>
          ))}
        </div>

        {/* Daily series */}
        {series.length > 0 ? (
          <div
            className="h-24 text-neutral-400 dark:text-neutral-500"
            data-testid="craft-tape-series-chart"
          >
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={series}
                margin={{ top: 4, right: 4, left: 4, bottom: 0 }}
              >
                <XAxis
                  dataKey="day"
                  tickFormatter={shortDay}
                  tick={{ fontSize: 10 }}
                  axisLine={false}
                  tickLine={false}
                  interval="preserveStartEnd"
                />
                <YAxis hide />
                <ChartTooltip
                  cursor={{ fill: "rgba(0,0,0,0.04)" }}
                  contentStyle={{ fontSize: 12, borderRadius: 8 }}
                />
                <Bar
                  dataKey="sessions"
                  fill="currentColor"
                  radius={[2, 2, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : null}
      </div>
    </Card>
  );
}

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-xs text-neutral-500 dark:text-neutral-400">
        {label}
      </span>
      <span className="text-xl font-medium leading-7">{value}</span>
    </div>
  );
}

function shortDay(day: string): string {
  const parts = day.split("-");
  return parts.length === 3 ? `${parts[1]}-${parts[2]}` : day;
}
