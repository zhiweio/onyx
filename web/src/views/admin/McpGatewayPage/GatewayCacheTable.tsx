"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useFormatter, useTranslations } from "next-intl";
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
import { errorMessage, formatBytes, PAGE_SIZE } from "./format";
import { useDebouncedValue } from "./useDebouncedValue";

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
  const format = useFormatter();
  const [searchInput, setSearchInput] = useState("");
  const searchTerm = useDebouncedValue(searchInput);
  const filterKey = `${catalogSlug}\0${tool}\0${searchTerm}`;
  const [filterSnapshot, setFilterSnapshot] = useState(filterKey);
  const [pageIndex, setPageIndex] = useState(0);
  const nextPageIndex = filterSnapshot !== filterKey ? 0 : pageIndex;
  if (filterSnapshot !== filterKey) {
    setFilterSnapshot(filterKey);
    setPageIndex(0);
  }
  const [rows, setRows] = useState<McpGatewayCacheEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const requestId = useRef(0);

  const load = useCallback(async () => {
    const id = ++requestId.current;
    setIsLoading(true);
    try {
      const result = await listMcpGatewayCache({
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
  }, [catalogSlug, tool, searchTerm, nextPageIndex, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const columns = useMemo(
    () => [
      tc.column("effective_tool_name", {
        header: t("cache.tool"),
        weight: 20,
        enableSorting: false,
        cell: (value) => value || "—",
      }),
      tc.column("catalog_slug", {
        header: t("cache.server"),
        weight: 16,
        enableSorting: false,
        cell: (value) => value || "—",
      }),
      tc.column("hit_count", {
        header: t("cache.hits"),
        weight: 8,
        enableSorting: false,
        cell: (value) => String(value ?? 0),
      }),
      tc.column("size_bytes", {
        header: t("cache.size"),
        weight: 10,
        enableSorting: false,
        cell: (value) => formatBytes(value),
      }),
      tc.column("last_accessed_at", {
        header: t("cache.lastAccess"),
        weight: 16,
        enableSorting: false,
        cell: (value) =>
          format.dateTime(new Date(value), {
            dateStyle: "short",
            timeStyle: "short",
          }),
      }),
      tc.column("last_refresh_status", {
        header: t("cache.status"),
        weight: 12,
        enableSorting: false,
        cell: (value) => value ?? "—",
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
                    return load();
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
    [format, load, t]
  );

  return (
    <div
      className="flex flex-col gap-3 pt-4"
      data-testid="mcp-gateway-cache-table"
    >
      <InputTypeIn
        searchIcon
        value={searchInput}
        onChange={(event) => setSearchInput(event.target.value)}
        placeholder={t("cache.searchPlaceholder")}
        aria-label={t("cache.searchPlaceholder")}
        data-testid="mcp-gateway-cache-search"
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
        serverSide={{
          totalItems: total,
          isLoading,
          onSortingChange: () => undefined,
          onPaginationChange: (nextPage) => setPageIndex(nextPage),
          onSearchTermChange: () => undefined,
        }}
      />
    </div>
  );
}
