"use client";

import { useEffect, useMemo } from "react";
import { useTranslations } from "next-intl";
import { InputTypeIn, Table, Tag, createTableColumns } from "@opal/components";
import { IllustrationContent, toast } from "@opal/layouts";
import SvgNoResult from "@opal/illustrations/no-result";
import {
  DateTimeCell,
  MetricCell,
  TruncatedTextCell,
} from "@/components/admin/TableCells";
import { useServerPaginatedTable } from "@/hooks/useServerPaginatedTable";
import { listTapeSessions } from "@/lib/craft-tape/api";
import type { TapeSessionItem } from "@/lib/craft-tape/types";
import { errorMessage } from "@/views/admin/McpGatewayPage/format";

const PAGE_SIZE = 20;

const tc = createTableColumns<TapeSessionItem>();

const KNOWN_REASONS = [
  "completed",
  "aborted",
  "error",
  "interrupted",
  "deadline_exceeded",
] as const;

type KnownReason = (typeof KNOWN_REASONS)[number];

const REASON_TAG_COLORS: Record<string, "green" | "red" | "amber" | "gray"> = {
  completed: "green",
  error: "red",
  aborted: "amber",
  interrupted: "amber",
  deadline_exceeded: "amber",
};

function isKnownReason(value: string): value is KnownReason {
  return (KNOWN_REASONS as readonly string[]).includes(value);
}

interface TapeSessionsTableProps {
  window: { from?: string; to?: string };
  origin: string;
  userQ?: string;
  sort?: string;
  order?: string;
  onSelect: (session: TapeSessionItem) => void;
}

export default function TapeSessionsTable({
  window,
  origin,
  userQ,
  sort,
  order,
  onSelect,
}: TapeSessionsTableProps) {
  const t = useTranslations("admin.craftTape");
  const { rows, isLoading, error, searchTerm, serverSide, searchInputProps } =
    useServerPaginatedTable<TapeSessionItem>({
      requestKey: `craft-tape\0${window.from ?? ""}\0${window.to ?? ""}\0${origin}\0${userQ ?? ""}\0${sort ?? ""}\0${order ?? ""}`,
      pageSize: PAGE_SIZE,
      loader: ({ offset, limit, q }) =>
        listTapeSessions({
          from: window.from,
          to: window.to,
          origin: origin || undefined,
          userQ: userQ || undefined,
          q,
          sort,
          order,
          offset,
          limit,
        }),
    });

  useEffect(() => {
    if (error) {
      toast.error(errorMessage(error, t("loadFailed")));
    }
  }, [error, t]);

  const columns = useMemo(
    () => [
      tc.column("created_at", {
        header: t("sessions.col.created"),
        weight: 13,
        enableSorting: false,
        cell: (value) =>
          value ? <DateTimeCell value={value} /> : <span>—</span>,
      }),
      tc.column("name", {
        header: t("sessions.col.name"),
        weight: 24,
        enableSorting: false,
        cell: (value, row) => (
          <TruncatedTextCell
            value={value ?? row.session_id.slice(0, 8)}
            empty=""
          />
        ),
      }),
      tc.column("user_email", {
        header: t("sessions.col.user"),
        weight: 16,
        enableSorting: false,
        cell: (value) => <TruncatedTextCell value={value} empty="—" />,
      }),
      tc.column("origin", {
        header: t("sessions.col.origin"),
        weight: 9,
        enableSorting: false,
        cell: (value) => <MetricCell value={value ?? "—"} />,
      }),
      tc.column("turns", {
        header: t("sessions.col.turns"),
        weight: 8,
        enableSorting: false,
        cell: (value) => <MetricCell value={String(value)} />,
      }),
      tc.column("events", {
        header: t("sessions.col.events"),
        weight: 9,
        enableSorting: false,
        cell: (value, row) => (
          <span>
            <MetricCell value={String(value)} />
            {row.hot_events > 0 ? (
              <span className="ml-1 text-xs text-neutral-500">
                +{row.hot_events}
              </span>
            ) : null}
          </span>
        ),
      }),
      tc.column("output_tokens", {
        header: t("sessions.col.tokens"),
        weight: 9,
        enableSorting: false,
        cell: (value) => <MetricCell value={value.toLocaleString()} />,
      }),
      tc.column("last_reason", {
        header: t("sessions.col.lastReason"),
        weight: 12,
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
    <div data-testid="craft-tape-sessions" className="flex flex-col gap-3 pt-2">
      <div className="max-w-sm">
        <InputTypeIn
          searchIcon
          placeholder={t("sessions.searchPlaceholder")}
          aria-label={t("sessions.searchPlaceholder")}
          data-testid="craft-tape-search"
          {...searchInputProps}
        />
      </div>
      <Table
        data={rows}
        columns={columns}
        getRowId={(row) => row.session_id}
        pageSize={PAGE_SIZE}
        variant="cards"
        searchTerm={searchTerm}
        footer={{ units: t("table.footerUnits") }}
        onRowClick={(row) => onSelect(row)}
        emptyState={
          <IllustrationContent
            illustration={SvgNoResult}
            title={isLoading ? t("table.loading") : t("sessions.empty")}
          />
        }
        serverSide={serverSide}
      />
    </div>
  );
}
