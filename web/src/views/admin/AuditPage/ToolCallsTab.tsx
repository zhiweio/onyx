"use client";

import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import {
  Button,
  Card,
  InputTypeIn,
  Modal,
  Table,
  Tag,
  Text,
  createTableColumns,
} from "@opal/components";
import { IllustrationContent, toast } from "@opal/layouts";
import SvgNoResult from "@opal/illustrations/no-result";
import { ADMIN_ROUTES } from "@/lib/admin-routes";
import { DetailField } from "@/components/admin/DetailField";
import { JsonBlock } from "@/components/admin/JsonBlock";
import {
  DateTimeCell,
  MetricCell,
  TruncatedTextCell,
} from "@/components/admin/TableCells";
import { useServerPaginatedTable } from "@/hooks/useServerPaginatedTable";
import { errorMessage } from "@/views/admin/McpGatewayPage/format";
import {
  csvCell,
  downloadCsv,
  EXPORT_ROW_LIMIT,
  fetchAuditToolCalls,
  type AuditToolCall,
  type AuditToolStat,
  type AuditWindow,
} from "./api";

const PAGE_SIZE = 20;

const tc = createTableColumns<AuditToolCall>();
const tcStats = createTableColumns<AuditToolStat>();

interface ToolCallsTabProps {
  window: AuditWindow;
}

interface CallDetailModalProps {
  row: AuditToolCall;
  onClose: () => void;
}

function CallDetailModal({ row, onClose }: CallDetailModalProps) {
  const t = useTranslations("admin.audit");
  return (
    <Modal open onOpenChange={(open) => !open && onClose()}>
      <Modal.Content width="lg" height="lg">
        <Modal.Header
          icon={ADMIN_ROUTES.AUDIT.icon}
          title={t("tools.detailTitle")}
          description={row.tool}
          onClose={onClose}
        />
        <Modal.Body>
          <div className="flex flex-col gap-4" data-testid="audit-call-detail">
            <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
              <DetailField
                label={t("tools.col.user")}
                value={row.user}
                empty={t("tools.notAvailable")}
                copyable
              />
              <DetailField
                label={t("tools.col.session")}
                value={row.session_id}
                empty={t("tools.notAvailable")}
                copyable
              />
              <DetailField
                label={t("tools.col.duration")}
                value={
                  row.duration_ms === null
                    ? null
                    : t("tools.latencyMs", { ms: row.duration_ms })
                }
                empty={t("tools.notAvailable")}
              />
              <DetailField
                label={t("tools.col.time")}
                value={new Date(row.created_at).toLocaleString()}
                empty={t("tools.notAvailable")}
              />
            </div>
            {row.result_excerpt ? (
              <div className="flex flex-col gap-2">
                <Text as="p" font="secondary-action">
                  {t("tools.result")}
                </Text>
                <Card padding={2} rounding={3} background="heavy">
                  <Text as="p" font="secondary-body" wordWrap="break-all">
                    {row.result_excerpt}
                  </Text>
                </Card>
              </div>
            ) : null}
            <div className="flex flex-col gap-2">
              <Text as="p" font="secondary-action">
                {t("tools.arguments")}
              </Text>
              <JsonBlock value={row.arguments ?? null} />
            </div>
          </div>
        </Modal.Body>
      </Modal.Content>
    </Modal>
  );
}

export default function ToolCallsTab({ window }: ToolCallsTabProps) {
  const t = useTranslations("admin.audit");
  const {
    searchInputProps,
    searchTerm,
    rows,
    isLoading,
    error,
    data,
    serverSide,
  } = useServerPaginatedTable<AuditToolCall>({
    requestKey: `tools\0${window.start}\0${window.end}`,
    pageSize: PAGE_SIZE,
    loader: ({ offset, limit, q }) =>
      fetchAuditToolCalls(window, { q, offset, limit }),
  });
  const [selectedRow, setSelectedRow] = useState<AuditToolCall | null>(null);
  const [isExporting, setIsExporting] = useState(false);

  useEffect(() => {
    if (error) {
      toast.error(errorMessage(error, t("loadFailed")));
    }
  }, [error, t]);

  const columns = useMemo(
    () => [
      tc.column("created_at", {
        header: t("tools.col.time"),
        weight: 14,
        enableSorting: false,
        cell: (value) => <DateTimeCell value={value} />,
      }),
      tc.column("user", {
        header: t("tools.col.user"),
        weight: 18,
        enableSorting: false,
        cell: (value) => <TruncatedTextCell value={value} empty="" />,
      }),
      tc.column("tool", {
        header: t("tools.col.tool"),
        weight: 22,
        enableSorting: false,
        cell: (value) => <TruncatedTextCell value={value} empty="" mono />,
      }),
      tc.column("ok", {
        header: t("tools.col.status"),
        weight: 9,
        enableSorting: false,
        cell: (value, row) =>
          row.ok ? (
            <Tag title={t("tools.ok")} color="green" />
          ) : (
            <Tag title={t("tools.fail")} color="red" />
          ),
      }),
      tc.column("duration_ms", {
        header: t("tools.col.duration"),
        weight: 10,
        enableSorting: false,
        cell: (value) => (
          <MetricCell
            value={value === null ? "-" : t("tools.latencyMs", { ms: value })}
          />
        ),
      }),
      tc.column("result_excerpt", {
        header: t("tools.col.result"),
        weight: 27,
        enableSorting: false,
        cell: (value) => <TruncatedTextCell value={value} empty="" />,
      }),
    ],
    [t]
  );

  const statsColumns = useMemo(
    () => [
      tcStats.column("tool", {
        header: t("col.tool"),
        weight: 40,
        enableSorting: false,
        cell: (value) => <TruncatedTextCell value={value} empty="" mono />,
      }),
      tcStats.column("calls", {
        header: t("col.calls"),
        weight: 20,
        enableSorting: false,
        cell: (value) => <MetricCell value={String(value)} />,
      }),
      tcStats.column("failures", {
        header: t("col.failures"),
        weight: 20,
        enableSorting: false,
        cell: (value) => <MetricCell value={String(value)} />,
      }),
      tcStats.column("avg_ms", {
        header: t("col.avgMs"),
        weight: 20,
        enableSorting: false,
        cell: (value) => (
          <MetricCell value={value === null ? "-" : String(value)} />
        ),
      }),
    ],
    [t]
  );

  const exportCsv = () => {
    setIsExporting(true);
    fetchAuditToolCalls(window, {
      q: searchTerm,
      offset: 0,
      limit: EXPORT_ROW_LIMIT,
    })
      .then((result) => {
        downloadCsv("audit-tool-calls.csv", [
          ["time", "user", "tool", "ok", "ms", "result"],
          ...result.items.map((call) => [
            csvCell(call.created_at),
            csvCell(call.user),
            csvCell(call.tool),
            call.ok ? "OK" : "FAIL",
            call.duration_ms === null ? "" : String(call.duration_ms),
            csvCell(call.result_excerpt),
          ]),
        ]);
      })
      .catch((exportError) =>
        toast.error(errorMessage(exportError, t("loadFailed")))
      )
      .finally(() => setIsExporting(false));
  };

  const stats = data?.stats ?? [];

  return (
    <div
      className="flex flex-col gap-3 pt-4"
      data-testid="audit-tool-calls-tab"
    >
      <div className="flex flex-wrap items-center gap-2">
        <div className="max-w-sm grow">
          <InputTypeIn
            searchIcon
            placeholder={t("tools.searchPlaceholder")}
            aria-label={t("tools.searchPlaceholder")}
            data-testid="audit-tool-calls-search"
            {...searchInputProps}
          />
        </div>
        <Button
          prominence="secondary"
          disabled={isExporting}
          onClick={() => exportCsv()}
        >
          {t("export")}
        </Button>
      </div>

      {stats.length > 0 ? (
        <Card padding={3} rounding={3}>
          <Text as="p" font="main-ui-body">
            {t("stats")}
          </Text>
          <Table
            data={stats}
            columns={statsColumns}
            getRowId={(row) => row.tool}
            variant="rows"
            pageSize={Infinity}
          />
        </Card>
      ) : null}

      <Table
        data={rows}
        columns={columns}
        getRowId={(row) => String(row.id)}
        pageSize={PAGE_SIZE}
        variant="cards"
        searchTerm={searchTerm}
        footer={{ units: t("table.footerUnits") }}
        onRowClick={(row) => setSelectedRow(row)}
        emptyState={
          <IllustrationContent
            illustration={SvgNoResult}
            title={isLoading ? t("table.loading") : t("tools.empty")}
          />
        }
        serverSide={serverSide}
      />
      {selectedRow ? (
        <CallDetailModal
          row={selectedRow}
          onClose={() => setSelectedRow(null)}
        />
      ) : null}
    </div>
  );
}
