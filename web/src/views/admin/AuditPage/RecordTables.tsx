"use client";

import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import {
  Button,
  InputTypeIn,
  Table,
  Tag,
  createTableColumns,
  type TagColor,
} from "@opal/components";
import { IllustrationContent, toast } from "@opal/layouts";
import SvgNoResult from "@opal/illustrations/no-result";
import { DateTimeCell, TruncatedTextCell } from "@/components/admin/TableCells";
import { useServerPaginatedTable } from "@/hooks/useServerPaginatedTable";
import { errorMessage } from "@/views/admin/McpGatewayPage/format";
import {
  csvCell,
  downloadCsv,
  EXPORT_ROW_LIMIT,
  fetchAuditApprovals,
  fetchAuditQueryHistory,
  fetchAuditQuarantines,
  type AuditApproval,
  type AuditQueryHistoryRow,
  type AuditQuarantine,
  type AuditWindow,
} from "./api";

const PAGE_SIZE = 20;

function decisionColor(decision: string | null): TagColor {
  switch (decision) {
    case "APPROVED":
    case "RELEASED":
      return "green";
    case "REJECTED":
      return "red";
    case "EXPIRED":
      return "amber";
    default:
      return "gray";
  }
}

interface RecordTabProps {
  window: AuditWindow;
}

function useRecordTable<T>(
  window: AuditWindow,
  requestKeyPrefix: string,
  loader: (
    window: AuditWindow,
    args: { q: string; offset: number; limit: number }
  ) => Promise<{ items: T[]; total_items: number }>,
  exportFilename: string,
  exportLoader: (window: AuditWindow, q: string) => Promise<string[][]>
) {
  const t = useTranslations("admin.audit");
  const table = useServerPaginatedTable<T>({
    requestKey: `${requestKeyPrefix}\0${window.start}\0${window.end}`,
    pageSize: PAGE_SIZE,
    loader: (args) =>
      loader(window, args).then((result) => ({
        items: result.items,
        total: result.total_items,
      })),
  });
  const [isExporting, setIsExporting] = useState(false);

  useEffect(() => {
    if (table.error) {
      toast.error(errorMessage(table.error, t("loadFailed")));
    }
  }, [table.error, t]);

  const exportCsv = () => {
    setIsExporting(true);
    exportLoader(window, table.searchTerm)
      .then((rows) => downloadCsv(exportFilename, rows))
      .catch((error) => toast.error(errorMessage(error, t("loadFailed"))))
      .finally(() => setIsExporting(false));
  };

  return { ...table, isExporting, exportCsv };
}

function RecordToolbar({
  searchPlaceholder,
  testId,
  isExporting,
  onExport,
  searchInputProps,
}: {
  searchPlaceholder: string;
  testId: string;
  isExporting: boolean;
  onExport: () => void;
  searchInputProps: {
    value: string;
    onChange: (event: React.ChangeEvent<HTMLInputElement>) => void;
  };
}) {
  const t = useTranslations("admin.audit");
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="max-w-sm grow">
        <InputTypeIn
          searchIcon
          placeholder={searchPlaceholder}
          aria-label={searchPlaceholder}
          data-testid={testId}
          {...searchInputProps}
        />
      </div>
      <Button prominence="secondary" disabled={isExporting} onClick={onExport}>
        {t("export")}
      </Button>
    </div>
  );
}

export function ApprovalsTab({ window }: RecordTabProps) {
  const t = useTranslations("admin.audit");
  const tc = useMemo(() => createTableColumns<AuditApproval>(), []);
  const table = useRecordTable<AuditApproval>(
    window,
    "approvals",
    fetchAuditApprovals,
    "audit-approvals.csv",
    (win, q) =>
      fetchAuditApprovals(win, { q, offset: 0, limit: EXPORT_ROW_LIMIT }).then(
        (result) => [
          ["time", "app", "decision", "decided_at"],
          ...result.items.map((row) => [
            csvCell(row.created_at),
            csvCell(row.app_name),
            row.decision ?? "pending",
            row.decided_at ? csvCell(row.decided_at) : "",
          ]),
        ]
      )
  );

  const columns = useMemo(
    () => [
      tc.column("created_at", {
        header: t("approvals.col.time"),
        weight: 16,
        enableSorting: false,
        cell: (value) => <DateTimeCell value={value} />,
      }),
      tc.column("app_name", {
        header: t("approvals.col.app"),
        weight: 24,
        enableSorting: false,
        cell: (value) => <TruncatedTextCell value={value} empty="" />,
      }),
      tc.column("session_id", {
        header: t("approvals.col.session"),
        weight: 30,
        enableSorting: false,
        cell: (value) => <TruncatedTextCell value={value} empty="" mono />,
      }),
      tc.column("decision", {
        header: t("approvals.col.decision"),
        weight: 14,
        enableSorting: false,
        cell: (value) => (
          <Tag title={value ?? t("pending")} color={decisionColor(value)} />
        ),
      }),
      tc.column("decided_at", {
        header: t("approvals.col.decidedAt"),
        weight: 16,
        enableSorting: false,
        cell: (value) => <DateTimeCell value={value ?? ""} />,
      }),
    ],
    [tc, t]
  );

  return (
    <div className="flex flex-col gap-3 pt-4" data-testid="audit-approvals-tab">
      <RecordToolbar
        searchPlaceholder={t("approvals.searchPlaceholder")}
        testId="audit-approvals-search"
        isExporting={table.isExporting}
        onExport={table.exportCsv}
        searchInputProps={table.searchInputProps}
      />
      <Table
        data={table.rows}
        columns={columns}
        getRowId={(row) => row.id}
        pageSize={PAGE_SIZE}
        variant="cards"
        searchTerm={table.searchTerm}
        footer={{ units: t("table.footerUnits") }}
        emptyState={
          <IllustrationContent
            illustration={SvgNoResult}
            title={table.isLoading ? t("table.loading") : t("approvals.empty")}
          />
        }
        serverSide={table.serverSide}
      />
    </div>
  );
}

export function QuarantinesTab({ window }: RecordTabProps) {
  const t = useTranslations("admin.audit");
  const tc = useMemo(() => createTableColumns<AuditQuarantine>(), []);
  const table = useRecordTable<AuditQuarantine>(
    window,
    "quarantines",
    fetchAuditQuarantines,
    "audit-quarantines.csv",
    (win, q) =>
      fetchAuditQuarantines(win, {
        q,
        offset: 0,
        limit: EXPORT_ROW_LIMIT,
      }).then((result) => [
        ["time", "url_hash", "verdict", "decision"],
        ...result.items.map((row) => [
          csvCell(row.created_at),
          csvCell(row.url_hash),
          csvCell(row.verdict),
          row.decision ?? "",
        ]),
      ])
  );

  const columns = useMemo(
    () => [
      tc.column("created_at", {
        header: t("quarantines.col.time"),
        weight: 16,
        enableSorting: false,
        cell: (value) => <DateTimeCell value={value} />,
      }),
      tc.column("url_hash", {
        header: t("quarantines.col.urlHash"),
        weight: 28,
        enableSorting: false,
        cell: (value) => <TruncatedTextCell value={value} empty="" mono />,
      }),
      tc.column("verdict", {
        header: t("quarantines.col.verdict"),
        weight: 14,
        enableSorting: false,
        cell: (value) => (
          <Tag title={value} color={value === "block" ? "red" : "amber"} />
        ),
      }),
      tc.column("decision", {
        header: t("quarantines.col.decision"),
        weight: 14,
        enableSorting: false,
        cell: (value) => (
          <Tag title={value ?? t("pending")} color={decisionColor(value)} />
        ),
      }),
      tc.column("session_id", {
        header: t("quarantines.col.session"),
        weight: 28,
        enableSorting: false,
        cell: (value) => <TruncatedTextCell value={value} empty="" mono />,
      }),
    ],
    [tc, t]
  );

  return (
    <div
      className="flex flex-col gap-3 pt-4"
      data-testid="audit-quarantines-tab"
    >
      <RecordToolbar
        searchPlaceholder={t("quarantines.searchPlaceholder")}
        testId="audit-quarantines-search"
        isExporting={table.isExporting}
        onExport={table.exportCsv}
        searchInputProps={table.searchInputProps}
      />
      <Table
        data={table.rows}
        columns={columns}
        getRowId={(row) => row.id}
        pageSize={PAGE_SIZE}
        variant="cards"
        searchTerm={table.searchTerm}
        footer={{ units: t("table.footerUnits") }}
        emptyState={
          <IllustrationContent
            illustration={SvgNoResult}
            title={
              table.isLoading ? t("table.loading") : t("quarantines.empty")
            }
          />
        }
        serverSide={table.serverSide}
      />
    </div>
  );
}

export function QueryHistoryTab({ window }: RecordTabProps) {
  const t = useTranslations("admin.audit");
  const tc = useMemo(() => createTableColumns<AuditQueryHistoryRow>(), []);
  const table = useRecordTable<AuditQueryHistoryRow>(
    window,
    "history",
    fetchAuditQueryHistory,
    "audit-query-history.csv",
    (win, q) =>
      fetchAuditQueryHistory(win, {
        q,
        offset: 0,
        limit: EXPORT_ROW_LIMIT,
      }).then((result) => [
        ["time", "user", "query"],
        ...result.items.map((row) => [
          csvCell(row.created_at),
          csvCell(row.user),
          csvCell(row.query),
        ]),
      ])
  );

  const columns = useMemo(
    () => [
      tc.column("created_at", {
        header: t("history.col.time"),
        weight: 16,
        enableSorting: false,
        cell: (value) => <DateTimeCell value={value} />,
      }),
      tc.column("user", {
        header: t("history.col.user"),
        weight: 22,
        enableSorting: false,
        cell: (value) => <TruncatedTextCell value={value} empty="" />,
      }),
      tc.column("query", {
        header: t("history.col.query"),
        weight: 62,
        enableSorting: false,
        cell: (value) => <TruncatedTextCell value={value} empty="" />,
      }),
    ],
    [tc, t]
  );

  return (
    <div className="flex flex-col gap-3 pt-4" data-testid="audit-history-tab">
      <RecordToolbar
        searchPlaceholder={t("history.searchPlaceholder")}
        testId="audit-history-search"
        isExporting={table.isExporting}
        onExport={table.exportCsv}
        searchInputProps={table.searchInputProps}
      />
      <Table
        data={table.rows}
        columns={columns}
        getRowId={(row) => `${row.user}\0${row.created_at}\0${row.query}`}
        pageSize={PAGE_SIZE}
        variant="cards"
        searchTerm={table.searchTerm}
        footer={{ units: t("table.footerUnits") }}
        emptyState={
          <IllustrationContent
            illustration={SvgNoResult}
            title={table.isLoading ? t("table.loading") : t("history.empty")}
          />
        }
        serverSide={table.serverSide}
      />
    </div>
  );
}
