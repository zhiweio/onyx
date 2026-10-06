"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import {
  Card,
  InputTypeIn,
  Table,
  Tag,
  createTableColumns,
} from "@opal/components";
import { SettingsLayouts, toast } from "@opal/layouts";
import { MetricCell } from "@/components/admin/TableCells";
import { ADMIN_ROUTES } from "@/lib/admin-routes";
import TapeSessionDetail from "@/components/craft-tape/TapeSessionDetail";
import { fetchTapeStats, fetchTapeStatsSeries } from "@/lib/craft-tape/api";
import type {
  TapeSessionItem,
  TapeStats,
  TapeStatsSeriesPoint,
} from "@/lib/craft-tape/types";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { errorMessage } from "@/views/admin/McpGatewayPage/format";
import TapeSessionsTable from "./TapeSessionsTable";

const ROUTE = ADMIN_ROUTES.CRAFT_TAPE;

const WINDOW_OPTIONS = [7, 30, 90] as const;

const ORIGINS = [
  "interactive",
  "scheduled",
  "slack",
  "job",
  "im",
  "eval",
] as const;

const SORT_OPTIONS = ["created_at", "name", "last_activity"] as const;

function isoDaysAgo(days: number): string {
  const date = new Date(Date.now() - days * 24 * 60 * 60 * 1000);
  return date.toISOString();
}

const seriesTc = createTableColumns<TapeStatsSeriesPoint>();

export default function CraftTapePage() {
  const t = useTranslations("admin.craftTape");
  const [days, setDays] = useState<number>(30);
  const [origin, setOrigin] = useState<string>("");
  const [userQInput, setUserQInput] = useState("");
  const userQ = useDebouncedValue(userQInput, 300);
  const [sort, setSort] = useState<string>("created_at");
  const [order, setOrder] = useState<string>("desc");
  const [stats, setStats] = useState<TapeStats | null>(null);
  const [series, setSeries] = useState<TapeStatsSeriesPoint[]>([]);
  const [selected, setSelected] = useState<TapeSessionItem | null>(null);

  const window = useMemo(
    () => ({ from: isoDaysAgo(days), to: new Date().toISOString() }),
    [days]
  );

  useEffect(() => {
    fetchTapeStats(window)
      .then(setStats)
      .catch((error) => toast.error(errorMessage(error, t("loadFailed"))));
    fetchTapeStatsSeries(window)
      .then((result) => setSeries(result.series))
      .catch(() => setSeries([]));
  }, [window, t]);

  const handleSelect = useCallback((session: TapeSessionItem) => {
    setSelected(session);
  }, []);

  const seriesColumns = useMemo(
    () => [
      seriesTc.column("day", {
        header: t("series.col.day"),
        weight: 25,
        enableSorting: false,
        cell: (value) => <MetricCell value={value} />,
      }),
      seriesTc.column("sessions", {
        header: t("series.col.sessions"),
        weight: 25,
        enableSorting: false,
        cell: (value) => <MetricCell value={String(value)} />,
      }),
      seriesTc.column("turns", {
        header: t("series.col.turns"),
        weight: 25,
        enableSorting: false,
        cell: (value) => <MetricCell value={String(value)} />,
      }),
      seriesTc.column("events", {
        header: t("series.col.events"),
        weight: 25,
        enableSorting: false,
        cell: (value) => <MetricCell value={String(value)} />,
      }),
    ],
    [t]
  );

  return (
    <SettingsLayouts.Root>
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
            <Card padding={3} rounding={3}>
              <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
                <div>
                  <div className="text-xs text-neutral-500">
                    {t("overview.sessions")}
                  </div>
                  <div className="text-xl font-medium">
                    {stats?.sessions ?? 0}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-neutral-500">
                    {t("overview.turns")}
                  </div>
                  <div className="text-xl font-medium">{stats?.turns ?? 0}</div>
                </div>
                <div>
                  <div className="text-xs text-neutral-500">
                    {t("overview.events")}
                  </div>
                  <div className="text-xl font-medium">
                    {stats?.events ?? 0}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-neutral-500">
                    {t("overview.outputTokens")}
                  </div>
                  <div className="text-xl font-medium">
                    {(stats?.output_tokens ?? 0).toLocaleString()}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-neutral-500">
                    {t("overview.cost")}
                  </div>
                  <div className="text-xl font-medium">
                    ${(stats?.cost ?? 0).toFixed(2)}
                  </div>
                </div>
              </div>
            </Card>
          )}

          <div className="flex flex-wrap items-center gap-2">
            {WINDOW_OPTIONS.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setDays(option)}
                className={`rounded-md border px-2 py-1 text-xs ${
                  days === option
                    ? "border-neutral-900 bg-neutral-900 text-white dark:border-neutral-100 dark:bg-neutral-100 dark:text-neutral-900"
                    : "border-neutral-300 text-neutral-600 dark:border-neutral-600 dark:text-neutral-300"
                }`}
                data-testid={`craft-tape-window-${option}`}
              >
                {t("filters.days", { days: option })}
              </button>
            ))}
            <select
              aria-label={t("filters.origin")}
              value={origin}
              onChange={(event) => setOrigin(event.target.value)}
              className="rounded-md border border-neutral-300 bg-transparent px-2 py-1 text-xs dark:border-neutral-600"
              data-testid="craft-tape-origin"
            >
              <option value="">{t("filters.allOrigins")}</option>
              {ORIGINS.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
            <select
              aria-label={t("filters.sort")}
              value={`${sort}:${order}`}
              onChange={(event) => {
                const [nextSort, nextOrder] = event.target.value.split(":");
                setSort(nextSort ?? "created_at");
                setOrder(nextOrder ?? "desc");
              }}
              className="rounded-md border border-neutral-300 bg-transparent px-2 py-1 text-xs dark:border-neutral-600"
              data-testid="craft-tape-sort"
            >
              {SORT_OPTIONS.flatMap((key) =>
                (["desc", "asc"] as const).map((dir) => (
                  <option key={`${key}:${dir}`} value={`${key}:${dir}`}>
                    {t(`filters.sortKey.${key}`)} {t(`filters.sortDir.${dir}`)}
                  </option>
                ))
              )}
            </select>
            <div className="w-56">
              <InputTypeIn
                searchIcon
                placeholder={t("filters.userPlaceholder")}
                aria-label={t("filters.user")}
                value={userQInput}
                onChange={(event) => setUserQInput(event.target.value)}
                data-testid="craft-tape-user-filter"
              />
            </div>
          </div>

          <TapeSessionsTable
            window={window}
            origin={origin}
            userQ={userQ}
            sort={sort}
            order={order}
            onSelect={handleSelect}
          />

          {selected ? (
            <TapeSessionDetail session={selected} variant="admin" />
          ) : null}

          {series.length > 0 ? (
            <Card padding={3} rounding={3}>
              <Table
                data={series}
                columns={seriesColumns}
                getRowId={(row) => row.day}
                pageSize={10}
                variant="rows"
              />
            </Card>
          ) : null}
        </div>
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
