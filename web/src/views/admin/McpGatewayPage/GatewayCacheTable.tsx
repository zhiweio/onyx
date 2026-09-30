"use client";

import { useEffect, useMemo } from "react";
import { useTranslations } from "next-intl";
import {
  Button,
  InputTypeIn,
  Table,
  createTableColumns,
} from "@opal/components";
import { IllustrationContent, toast } from "@opal/layouts";
import SvgNoResult from "@opal/illustrations/no-result";
import {
  invalidateMcpGatewayCache,
  listMcpGatewayCache,
  refreshMcpGatewayCache,
} from "@/lib/mcp-catalog/api";
import type { McpGatewayCacheEntry } from "@/lib/mcp-catalog/types";
import { useServerPaginatedTable } from "@/hooks/useServerPaginatedTable";
import { errorMessage, formatBytes, PAGE_SIZE } from "./format";
import {
  DateTimeCell,
  MetricCell,
  RefreshStatusTag,
  ServerTagCell,
  TruncatedTextCell,
} from "./GatewayTableCells";

const tc = createTableColumns<McpGatewayCacheEntry>();

interface GatewayCacheTableProps {
  catalogSlug: string;
  tool: string;
}

export default function GatewayCacheTable({
  catalogSlug,
  tool,
}: GatewayCacheTableProps) {
  const t = useTranslations("admin.mcpGateway");
  const {
    searchInputProps,
    searchTerm,
    rows,
    isLoading,
    error,
    reload,
    serverSide,
  } = useServerPaginatedTable<McpGatewayCacheEntry>({
    requestKey: `${catalogSlug}\0${tool}`,
    pageSize: PAGE_SIZE,
    loader: ({ offset, limit, q }) =>
      listMcpGatewayCache({
        catalog_slug: catalogSlug || undefined,
        tool: tool || undefined,
        q: q || undefined,
        offset,
        limit,
      }),
  });

  useEffect(() => {
    if (error) {
      toast.error(errorMessage(error, t("toasts.loadFailed")));
    }
  }, [error, t]);

  const columns = useMemo(
    () => [
      tc.column("effective_tool_name", {
        header: t("cache.tool"),
        weight: 22,
        enableSorting: false,
        cell: (value) => (
          <TruncatedTextCell value={value} empty={t("calls.missing")} mono />
        ),
      }),
      tc.column("catalog_slug", {
        header: t("cache.server"),
        weight: 14,
        enableSorting: false,
        cell: (value) => (
          <ServerTagCell value={value} empty={t("calls.missing")} />
        ),
      }),
      tc.column("hit_count", {
        header: t("cache.hits"),
        weight: 8,
        enableSorting: false,
        cell: (value) => <MetricCell value={String(value ?? 0)} />,
      }),
      tc.column("size_bytes", {
        header: t("cache.size"),
        weight: 8,
        enableSorting: false,
        cell: (value) => <MetricCell value={formatBytes(value)} />,
      }),
      tc.column("last_accessed_at", {
        header: t("cache.lastAccess"),
        weight: 12,
        enableSorting: false,
        cell: (value) => <DateTimeCell value={value} timeStyle="short" />,
      }),
      tc.column("last_refresh_status", {
        header: t("cache.status"),
        weight: 10,
        enableSorting: false,
        cell: (value) => (
          <RefreshStatusTag status={value} empty={t("calls.missing")} />
        ),
      }),
      tc.actions({
        showColumnVisibility: false,
        showSorting: false,
        cell: (row) => (
          <div className="flex gap-2">
            <Button
              prominence="internal"
              onClick={() =>
                void invalidateMcpGatewayCache({ cache_key: row.cache_key })
                  .then(() => {
                    toast.success(t("toasts.invalidated"));
                    return reload();
                  })
                  .catch((error) =>
                    toast.error(errorMessage(error, t("toasts.loadFailed")))
                  )
              }
            >
              {t("cache.invalidate")}
            </Button>
            <Button
              prominence="internal"
              onClick={() =>
                void refreshMcpGatewayCache(row.cache_key)
                  .then(() => toast.success(t("toasts.refreshed")))
                  .catch((error) =>
                    toast.error(errorMessage(error, t("toasts.loadFailed")))
                  )
              }
            >
              {t("cache.refresh")}
            </Button>
          </div>
        ),
      }),
    ],
    [reload, t]
  );

  return (
    <div
      className="flex flex-col gap-3 pt-4"
      data-testid="mcp-gateway-cache-table"
    >
      <InputTypeIn
        searchIcon
        placeholder={t("cache.searchPlaceholder")}
        aria-label={t("cache.searchPlaceholder")}
        data-testid="mcp-gateway-cache-search"
        {...searchInputProps}
      />
      <Table
        key={`${catalogSlug}|${tool}`}
        data={rows}
        columns={columns}
        getRowId={(row) => row.cache_key}
        pageSize={PAGE_SIZE}
        variant="cards"
        searchTerm={searchTerm}
        footer={{ units: t("table.footerUnits") }}
        emptyState={
          <IllustrationContent
            illustration={SvgNoResult}
            title={isLoading ? t("table.loading") : t("cache.empty")}
          />
        }
        serverSide={serverSide}
      />
    </div>
  );
}
