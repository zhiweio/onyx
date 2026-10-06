"use client";

/**
 * Personal execution-tape entry (/craft/v1/tapes): the signed-in user's own
 * craft sessions — task-name search, time window, origin, sorting — with the
 * shared detail (turn table + event timeline + cinematic replay + export).
 * Server-side every read is ownership-scoped (/build/tape).
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import {
  Button,
  Card,
  InputTypeIn,
  Table,
  Tag,
  createTableColumns,
} from "@opal/components";
import { SvgHistory } from "@opal/icons";
import { IllustrationContent, SettingsLayouts, toast } from "@opal/layouts";
import SvgNoResult from "@opal/illustrations/no-result";
import {
  DateTimeCell,
  MetricCell,
  TruncatedTextCell,
} from "@/components/admin/TableCells";
import TapeSessionDetail from "@/components/craft-tape/TapeSessionDetail";
import { useServerPaginatedTable } from "@/hooks/useServerPaginatedTable";
import { listMyTapeSessions } from "@/lib/craft-tape/api";
import type { TapeSessionItem } from "@/lib/craft-tape/types";
import { errorMessage } from "@/views/admin/McpGatewayPage/format";

const PAGE_SIZE = 20;

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

const REASON_TAG_COLORS: Record<string, "green" | "red" | "amber" | "gray"> = {
  completed: "green",
  error: "red",
  aborted: "amber",
  interrupted: "amber",
  deadline_exceeded: "amber",
};

const KNOWN_REASONS = [
  "completed",
  "aborted",
  "error",
  "interrupted",
  "deadline_exceeded",
] as const;

type KnownReason = (typeof KNOWN_REASONS)[number];

function isKnownReason(value: string): value is KnownReason {
  return (KNOWN_REASONS as readonly string[]).includes(value);
}

function isoDaysAgo(days: number): string {
  const date = new Date(Date.now() - days * 24 * 60 * 60 * 1000);
  return date.toISOString();
}

const tc = createTableColumns<TapeSessionItem>();

export default function CraftTapesPage() {
  const t = useTranslations("craftTape");
  const [days, setDays] = useState<number>(30);
  const [origin, setOrigin] = useState<string>("");
  const [sort, setSort] = useState<string>("created_at");
  const [order, setOrder] = useState<string>("desc");
  const [selected, setSelected] = useState<TapeSessionItem | null>(null);

  const timeWindow = useMemo(
    () => ({ from: isoDaysAgo(days), to: new Date().toISOString() }),
    [days]
  );

  const handleSelect = useCallback((session: TapeSessionItem) => {
    setSelected(session);
  }, []);

  const { rows, isLoading, error, searchTerm, serverSide, searchInputProps } =
    useServerPaginatedTable<TapeSessionItem>({
      requestKey: `my-craft-tape\0${timeWindow.from ?? ""}\0${timeWindow.to ?? ""}\0${origin}\0${sort}\0${order}`,
      pageSize: PAGE_SIZE,
      loader: ({ offset, limit, q }) =>
        listMyTapeSessions({
          from: timeWindow.from,
          to: timeWindow.to,
          origin: origin || undefined,
          q,
          sort,
          order,
          offset,
          limit,
        }),
    });

  const columns = useMemo(
    () => [
      tc.column("created_at", {
        header: t("sessions.col.created"),
        weight: 14,
        enableSorting: false,
        cell: (value) =>
          value ? <DateTimeCell value={value} /> : <span>—</span>,
      }),
      tc.column("name", {
        header: t("sessions.col.name"),
        weight: 30,
        enableSorting: false,
        cell: (value, row) => (
          <TruncatedTextCell
            value={value ?? row.session_id.slice(0, 8)}
            empty=""
          />
        ),
      }),
      tc.column("origin", {
        header: t("sessions.col.origin"),
        weight: 10,
        enableSorting: false,
        cell: (value) => <MetricCell value={value ?? "—"} />,
      }),
      tc.column("turns", {
        header: t("sessions.col.turns"),
        weight: 9,
        enableSorting: false,
        cell: (value) => <MetricCell value={String(value)} />,
      }),
      tc.column("events", {
        header: t("sessions.col.events"),
        weight: 10,
        enableSorting: false,
        cell: (value) => <MetricCell value={String(value)} />,
      }),
      tc.column("output_tokens", {
        header: t("sessions.col.tokens"),
        weight: 10,
        enableSorting: false,
        cell: (value) => <MetricCell value={value.toLocaleString()} />,
      }),
      tc.column("last_reason", {
        header: t("sessions.col.lastReason"),
        weight: 17,
        enableSorting: false,
        cell: (value) =>
          value ? (
            <Tag
              title={isKnownReason(value) ? t(`reasons.${value}`) : value}
              color={REASON_TAG_COLORS[value] ?? "gray"}
            />
          ) : (
            <span>—</span>
          ),
      }),
    ],
    [t]
  );

  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header
        icon={SvgHistory}
        title={t("myPage.title")}
        description={t("myPage.description")}
        divider
      />
      <SettingsLayouts.Body>
        <div className="flex flex-col gap-4" data-testid="my-craft-tapes-page">
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
                data-testid={`my-tapes-window-${option}`}
              >
                {t("filters.days", { days: option })}
              </button>
            ))}
            <select
              aria-label={t("filters.origin")}
              value={origin}
              onChange={(event) => setOrigin(event.target.value)}
              className="rounded-md border border-neutral-300 bg-transparent px-2 py-1 text-xs dark:border-neutral-600"
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
            >
              {SORT_OPTIONS.flatMap((key) =>
                (["desc", "asc"] as const).map((dir) => (
                  <option key={`${key}:${dir}`} value={`${key}:${dir}`}>
                    {t(`filters.sortKey.${key}`)} {t(`filters.sortDir.${dir}`)}
                  </option>
                ))
              )}
            </select>
            <div className="max-w-xs grow">
              <InputTypeIn
                searchIcon
                placeholder={t("myPage.searchPlaceholder")}
                aria-label={t("myPage.searchPlaceholder")}
                data-testid="my-tapes-search"
                {...searchInputProps}
              />
            </div>
          </div>

          <Card padding={3} rounding={3}>
            <Table
              data={rows}
              columns={columns}
              getRowId={(row) => row.session_id}
              pageSize={PAGE_SIZE}
              variant="cards"
              searchTerm={searchTerm}
              footer={{ units: t("table.footerUnits") }}
              onRowClick={handleSelect}
              emptyState={
                <IllustrationContent
                  illustration={SvgNoResult}
                  title={isLoading ? t("table.loading") : t("myPage.empty")}
                />
              }
              serverSide={serverSide}
            />
          </Card>

          {selected ? (
            <TapeSessionDetail session={selected} variant="personal" />
          ) : null}

          <div>
            {selected ? (
              <Button prominence="secondary" onClick={() => setSelected(null)}>
                {t("myPage.clearSelection")}
              </Button>
            ) : null}
          </div>
        </div>
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
