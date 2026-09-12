"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useFormatter, useTranslations } from "next-intl";
import {
  InputTypeIn,
  Modal,
  Table,
  createTableColumns,
} from "@opal/components";
import { IllustrationContent, toast } from "@opal/layouts";
import Text from "@/refresh-components/texts/Text";
import SvgNoResult from "@opal/illustrations/no-result";
import { ADMIN_ROUTES } from "@/lib/admin-routes";
import { getMcpGatewayCall, listMcpGatewayCalls } from "@/lib/mcp-catalog/api";
import type {
  McpGatewayCallDetail,
  McpGatewayCallItem,
} from "@/lib/mcp-catalog/types";
import type { DateRange } from "@/refresh-components/DateRangePicker";
import { isoWindowForInclusiveDateRange } from "./dateWindow";
import { errorMessage, formatBytes, PAGE_SIZE } from "./format";
import { useDebouncedValue } from "./useDebouncedValue";

const tc = createTableColumns<McpGatewayCallItem>();

interface GatewayCallsTableProps {
  dateRange: DateRange;
  catalogSlug: string;
  tool: string;
}

function outcomeLabel(
  t: ReturnType<typeof useTranslations<"admin.mcpGateway">>,
  outcome: string
): string {
  switch (outcome) {
    case "hit":
      return t("calls.outcomes.hit");
    case "miss":
      return t("calls.outcomes.miss");
    case "swr":
      return t("calls.outcomes.swr");
    case "refresh":
      return t("calls.outcomes.refresh");
    case "bypass":
      return t("calls.outcomes.bypass");
    case "error":
      return t("calls.outcomes.error");
    default:
      return outcome;
  }
}

function DetailField({
  label,
  value,
  empty,
}: {
  label: string;
  value: string | null | undefined;
  empty: string;
}) {
  return (
    <div className="flex flex-col gap-1">
      <Text as="p" secondaryBody text03>
        {label}
      </Text>
      <Text as="p" mainUiMono>
        {value || empty}
      </Text>
    </div>
  );
}

export default function GatewayCallsTable({
  dateRange,
  catalogSlug,
  tool,
}: GatewayCallsTableProps) {
  const t = useTranslations("admin.mcpGateway");
  const format = useFormatter();
  const [searchInput, setSearchInput] = useState("");
  const searchTerm = useDebouncedValue(searchInput);
  const isoWindow =
    dateRange?.from && dateRange.to
      ? isoWindowForInclusiveDateRange(dateRange)
      : undefined;
  const fromIso = isoWindow?.from;
  const toIso = isoWindow?.to;
  const filterKey = `${fromIso}\0${toIso}\0${catalogSlug}\0${tool}\0${searchTerm}`;
  const [filterSnapshot, setFilterSnapshot] = useState(filterKey);
  const [pageIndex, setPageIndex] = useState(0);
  const nextPageIndex = filterSnapshot !== filterKey ? 0 : pageIndex;
  if (filterSnapshot !== filterKey) {
    setFilterSnapshot(filterKey);
    setPageIndex(0);
  }
  const [rows, setRows] = useState<McpGatewayCallItem[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [detail, setDetail] = useState<McpGatewayCallDetail | null>(null);
  const requestId = useRef(0);

  const load = useCallback(async () => {
    if (!fromIso || !toIso) return;
    const id = ++requestId.current;
    setIsLoading(true);
    try {
      const result = await listMcpGatewayCalls({
        from: fromIso,
        to: toIso,
        catalog_slug: catalogSlug || undefined,
        tool: tool || undefined,
        q: searchTerm || undefined,
        offset: nextPageIndex * PAGE_SIZE,
        limit: PAGE_SIZE,
      });
      if (id !== requestId.current) return;
      setRows(result.items);
      setTotal(result.total);
    } catch (error) {
      if (id !== requestId.current) return;
      toast.error(errorMessage(error, t("toasts.loadFailed")));
    } finally {
      if (id === requestId.current) setIsLoading(false);
    }
  }, [fromIso, toIso, catalogSlug, tool, searchTerm, nextPageIndex, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const columns = useMemo(
    () => [
      tc.column("created_at", {
        header: t("calls.time"),
        weight: 16,
        enableSorting: false,
        cell: (value) =>
          format.dateTime(new Date(value), {
            dateStyle: "short",
            timeStyle: "medium",
          }),
      }),
      tc.column("catalog_slug", {
        header: t("calls.server"),
        weight: 12,
        enableSorting: false,
        cell: (value) => value || "—",
      }),
      tc.column("effective_tool_name", {
        header: t("calls.tool"),
        weight: 14,
        enableSorting: false,
        cell: (value) => value || "—",
      }),
      tc.column("outcome", {
        header: t("calls.outcome"),
        weight: 12,
        enableSorting: false,
        cell: (value) => outcomeLabel(t, value),
      }),
      tc.column("latency_ms", {
        header: t("calls.latency"),
        weight: 8,
        enableSorting: false,
        cell: (value) => t("calls.latencyMs", { ms: value }),
      }),
      tc.column("response_bytes", {
        header: t("calls.size"),
        weight: 8,
        enableSorting: false,
        cell: (value) => formatBytes(value),
      }),
      tc.column("upstream_billed", {
        header: t("calls.billed"),
        weight: 8,
        enableSorting: false,
        cell: (value) => (value ? t("calls.billedYes") : t("calls.billedNo")),
      }),
      tc.column("arguments_preview", {
        header: t("calls.preview"),
        weight: 22,
        enableSorting: false,
        cell: (value) => value || "—",
      }),
    ],
    [format, t]
  );

  return (
    <div
      className="flex flex-col gap-3 pt-4"
      data-testid="mcp-gateway-calls-table"
    >
      <InputTypeIn
        searchIcon
        value={searchInput}
        onChange={(event) => setSearchInput(event.target.value)}
        placeholder={t("calls.searchPlaceholder")}
        aria-label={t("calls.searchPlaceholder")}
        data-testid="mcp-gateway-calls-search"
      />
      <Table
        key={`${fromIso}|${toIso}|${catalogSlug}|${tool}`}
        data={rows}
        columns={columns}
        getRowId={(row) => String(row.id)}
        pageSize={PAGE_SIZE}
        variant="cards"
        searchTerm={searchTerm}
        footer={{ units: t("table.footerUnits") }}
        onRowClick={(row) =>
          void getMcpGatewayCall(row.id)
            .then(setDetail)
            .catch((error) =>
              toast.error(errorMessage(error, t("toasts.loadFailed")))
            )
        }
        emptyState={
          <IllustrationContent
            illustration={SvgNoResult}
            title={isLoading ? t("table.loading") : t("calls.empty")}
          />
        }
        serverSide={{
          totalItems: total,
          isLoading,
          onSortingChange: () => undefined,
          onPaginationChange: (nextPage) => setPageIndex(nextPage),
          onSearchTermChange: () => undefined,
        }}
      />
      {detail ? (
        <Modal open onOpenChange={(open) => !open && setDetail(null)}>
          <Modal.Content width="lg">
            <Modal.Header
              icon={ADMIN_ROUTES.MCP_GATEWAY.icon}
              title={t("calls.detailTitle")}
              onClose={() => setDetail(null)}
            />
            <Modal.Body>
              <div
                className="flex flex-col gap-4"
                data-testid="mcp-gateway-call-detail"
              >
                <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                  <DetailField
                    label={t("calls.requestId")}
                    value={detail.request_id}
                    empty={t("calls.missing")}
                  />
                  <DetailField
                    label={t("calls.parentCallId")}
                    value={detail.parent_call_id}
                    empty={t("calls.missing")}
                  />
                  <DetailField
                    label={t("calls.cacheKey")}
                    value={detail.cache_key}
                    empty={t("calls.missing")}
                  />
                  <DetailField
                    label={t("calls.userEmail")}
                    value={detail.user_email}
                    empty={t("calls.missing")}
                  />
                  <DetailField
                    label={t("calls.sessionId")}
                    value={detail.session_id}
                    empty={t("calls.missing")}
                  />
                  <DetailField
                    label={t("calls.packSlug")}
                    value={detail.pack_slug}
                    empty={t("calls.missing")}
                  />
                  <DetailField
                    label={t("calls.refreshMode")}
                    value={detail.refresh_mode}
                    empty={t("calls.missing")}
                  />
                  <DetailField
                    label={t("calls.resultBlobId")}
                    value={detail.result_blob_id}
                    empty={t("calls.missing")}
                  />
                </div>
                <div className="flex flex-col gap-1">
                  <Text as="p" secondaryBody text03>
                    {t("calls.arguments")}
                  </Text>
                  <pre className="max-h-56 overflow-auto text-sm">
                    {JSON.stringify(detail.arguments, null, 2)}
                  </pre>
                </div>
                <div className="flex flex-col gap-1">
                  <Text as="p" secondaryBody text03>
                    {t("calls.payload")}
                  </Text>
                  <pre className="max-h-56 overflow-auto text-sm">
                    {JSON.stringify(detail.payload ?? null, null, 2)}
                  </pre>
                </div>
              </div>
            </Modal.Body>
          </Modal.Content>
        </Modal>
      ) : null}
    </div>
  );
}
