"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Button, Text } from "@opal/components";
import { SettingsLayouts, toast } from "@opal/layouts";
import { SvgMcp } from "@opal/icons";
import {
  getMcpGatewayStats,
  invalidateMcpGatewayCache,
  listMcpCatalogEntries,
  listMcpGatewayCache,
  refreshMcpGatewayCache,
} from "@/lib/mcp-catalog/api";
import type {
  McpCatalogEntry,
  McpGatewayCacheEntry,
  McpGatewayStats,
} from "@/lib/mcp-catalog/types";
import { ADMIN_ROUTES } from "@/lib/admin-routes";

const route = ADMIN_ROUTES.MCP_GATEWAY;

function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let size = value / 1024;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size.toFixed(1)} ${units[unit]}`;
}

function errorMessage(error: Error | unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

export default function McpGatewayPage() {
  const t = useTranslations("admin.mcpGateway");
  const [entries, setEntries] = useState<McpCatalogEntry[]>([]);
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  const [cacheEntries, setCacheEntries] = useState<McpGatewayCacheEntry[]>([]);
  const [stats, setStats] = useState<McpGatewayStats | null>(null);

  const loadSelected = useCallback(async (catalogSlug: string | null) => {
    const [cacheRows, usage] = await Promise.all([
      listMcpGatewayCache(catalogSlug ?? undefined),
      getMcpGatewayStats(catalogSlug ?? undefined),
    ]);
    setCacheEntries(cacheRows);
    setStats(usage);
  }, []);

  useEffect(() => {
    void listMcpCatalogEntries()
      .then(setEntries)
      .catch((error) =>
        toast.error(errorMessage(error, t("toasts.loadFailed")))
      );
  }, [t]);

  useEffect(() => {
    void loadSelected(selectedSlug).catch((error) =>
      toast.error(errorMessage(error, t("toasts.loadFailed")))
    );
  }, [selectedSlug, loadSelected, t]);

  async function handleInvalidate(cacheKey: string) {
    try {
      await invalidateMcpGatewayCache({ cache_key: cacheKey });
      await loadSelected(selectedSlug);
      toast.success(t("toasts.invalidated"));
    } catch (error) {
      toast.error(errorMessage(error, t("toasts.invalidated")));
    }
  }

  async function handleRefresh(cacheKey: string) {
    try {
      await refreshMcpGatewayCache(cacheKey);
      toast.success(t("toasts.refreshed"));
    } catch (error) {
      toast.error(errorMessage(error, t("toasts.refreshed")));
    }
  }

  return (
    <SettingsLayouts.Root width="lg">
      <SettingsLayouts.Header
        icon={route.icon ?? SvgMcp}
        title={t("header.title")}
        description={t("header.description")}
        divider
      />
      <SettingsLayouts.Body>
        <div className="flex flex-col gap-8">
          <section className="flex flex-col gap-3">
            <Text>{t("filter.title")}</Text>
            <div className="flex flex-wrap gap-2">
              <Button
                prominence={selectedSlug === null ? "primary" : "secondary"}
                onClick={() => setSelectedSlug(null)}
              >
                {t("filter.all")}
              </Button>
              {entries.map((entry) => (
                <Button
                  key={entry.id}
                  prominence={
                    entry.slug === selectedSlug ? "primary" : "secondary"
                  }
                  onClick={() => setSelectedSlug(entry.slug)}
                >
                  {entry.display_name}
                </Button>
              ))}
            </div>
            {entries.length === 0 && (
              <Text color="text-02">{t("filter.empty")}</Text>
            )}
          </section>

          {stats && (
            <>
              <section className="flex flex-col gap-3">
                <Text>{t("stats.title")}</Text>
                <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
                  <Text color="text-02">{`${t("stats.total")}: ${stats.total_calls}`}</Text>
                  <Text color="text-02">{`${t("stats.hits")}: ${stats.cache_hits}`}</Text>
                  <Text color="text-02">{`${t("stats.billed")}: ${stats.upstream_billed}`}</Text>
                  <Text color="text-02">{`${t("stats.saved")}: ${stats.saved_calls}`}</Text>
                  <Text color="text-02">{`${t("stats.hitRate")}: ${formatPercent(stats.hit_rate)}`}</Text>
                </div>
              </section>

              <section className="flex flex-col gap-3">
                <Text>{t("storage.title")}</Text>
                <Text color="text-02">{t("storage.description")}</Text>
                <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
                  <Text color="text-02">{`${t("storage.results")}: ${stats.blob_total_count}`}</Text>
                  <Text color="text-02">{`${t("storage.stored")}: ${formatBytes(stats.blob_total_bytes)}`}</Text>
                  <Text color="text-02">{`${t("storage.transferred")}: ${formatBytes(stats.total_response_bytes)}`}</Text>
                </div>
                <div className="flex flex-wrap gap-3">
                  {Object.entries(stats.blob_by_storage).map(
                    ([tier, usage]) => (
                      <Text key={tier} color="text-02">
                        {`${tier}: ${usage.count} · ${formatBytes(usage.bytes)}`}
                      </Text>
                    )
                  )}
                </div>
              </section>
            </>
          )}

          <section className="flex flex-col gap-3">
            <Text>{t("cache.title")}</Text>
            {cacheEntries.length === 0 ? (
              <Text color="text-02">{t("cache.empty")}</Text>
            ) : (
              cacheEntries.map((entry) => (
                <div
                  key={entry.cache_key}
                  className="flex items-center justify-between gap-3 rounded-lg border border-border-02 px-3 py-2"
                >
                  <div className="flex flex-col">
                    <Text>{entry.effective_tool_name}</Text>
                    <Text color="text-02">
                      {`${entry.catalog_slug} · ${t("cache.hits")} ${entry.hit_count} · ${entry.storage} · ${formatBytes(entry.size_bytes)}`}
                    </Text>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      prominence="secondary"
                      onClick={() => void handleInvalidate(entry.cache_key)}
                    >
                      {t("cache.invalidate")}
                    </Button>
                    <Button
                      prominence="secondary"
                      onClick={() => void handleRefresh(entry.cache_key)}
                    >
                      {t("cache.refresh")}
                    </Button>
                  </div>
                </div>
              ))
            )}
          </section>
        </div>
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
