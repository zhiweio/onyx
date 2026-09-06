"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { Button, InputTypeIn, Switch, Tabs } from "@opal/components";
import Text from "@/refresh-components/texts/Text";
import { SettingsLayouts, toast } from "@opal/layouts";
import {
  getMcpGatewayStats,
  invalidateMcpGatewayCache,
  listMcpGatewayCache,
  listMcpGatewayCalls,
  refreshMcpGatewayCache,
} from "@/lib/mcp-catalog/api";
import type {
  McpGatewayCacheEntry,
  McpGatewayCallItem,
  McpGatewayStats,
} from "@/lib/mcp-catalog/types";
import InputSelect from "@/refresh-components/inputs/InputSelect";
import { ADMIN_ROUTES } from "@/lib/admin-routes";
import { useAdminMcpServers } from "@/lib/tools/hooks";
import { useSettings } from "@/lib/settings/hooks";
import { updateAdminSettings } from "@/lib/settings/svc";
import { mutate } from "swr";
import { SWR_KEYS } from "@/lib/swr-keys";

const route = ADMIN_ROUTES.MCP_GATEWAY;

type GatewayTab = "overview" | "cache" | "calls";

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

function windowRange(kind: "24h" | "7d") {
  const to = new Date();
  const from = new Date(
    kind === "24h"
      ? to.getTime() - 24 * 60 * 60 * 1000
      : to.getTime() - 7 * 24 * 60 * 60 * 1000
  );
  return { from: from.toISOString(), to: to.toISOString() };
}

export default function McpGatewayPage() {
  const t = useTranslations("admin.mcpGateway");
  const router = useRouter();
  const searchParams = useSearchParams();
  const settings = useSettings();
  const { mcpData } = useAdminMcpServers();
  const boundServers = useMemo(
    () => (mcpData?.mcp_servers ?? []).filter((server) => server.gateway_bound),
    [mcpData?.mcp_servers]
  );

  const tabParam = searchParams.get("tab");
  const tab: GatewayTab =
    tabParam === "cache" || tabParam === "calls" || tabParam === "overview"
      ? tabParam
      : "overview";
  const selectedSlug = searchParams.get("server") || "";
  const [windowKind, setWindowKind] = useState<"24h" | "7d">("24h");
  const range = useMemo(() => windowRange(windowKind), [windowKind]);

  const [stats, setStats] = useState<McpGatewayStats | null>(null);
  const [cacheRows, setCacheRows] = useState<McpGatewayCacheEntry[]>([]);
  const [cacheCursor, setCacheCursor] = useState<string | null>(null);
  const [callRows, setCallRows] = useState<McpGatewayCallItem[]>([]);
  const [callCursor, setCallCursor] = useState<string | null>(null);
  const [toolFilter, setToolFilter] = useState("");

  const setQuery = useCallback(
    (next: Record<string, string | null>) => {
      const params = new URLSearchParams(searchParams.toString());
      for (const [key, value] of Object.entries(next)) {
        if (value) params.set(key, value);
        else params.delete(key);
      }
      router.replace(`${ADMIN_ROUTES.MCP_GATEWAY.path}?${params.toString()}`);
    },
    [router, searchParams]
  );

  const loadStats = useCallback(async () => {
    const usage = await getMcpGatewayStats({
      from: range.from,
      to: range.to,
      catalog_slug: selectedSlug || undefined,
    });
    setStats(usage);
  }, [range.from, range.to, selectedSlug]);

  const loadCache = useCallback(
    async (cursor?: string) => {
      const result = await listMcpGatewayCache({
        catalog_slug: selectedSlug || undefined,
        tool: toolFilter || undefined,
        cursor,
        limit: 50,
      });
      setCacheRows((prev) =>
        cursor ? [...prev, ...result.items] : result.items
      );
      setCacheCursor(result.next_cursor);
    },
    [selectedSlug, toolFilter]
  );

  const loadCalls = useCallback(
    async (cursor?: string) => {
      const result = await listMcpGatewayCalls({
        from: range.from,
        to: range.to,
        catalog_slug: selectedSlug || undefined,
        tool: toolFilter || undefined,
        cursor,
      });
      setCallRows((prev) =>
        cursor ? [...prev, ...result.items] : result.items
      );
      setCallCursor(result.next_cursor);
    },
    [range.from, range.to, selectedSlug, toolFilter]
  );

  useEffect(() => {
    void loadStats().catch((error) =>
      toast.error(errorMessage(error, t("toasts.loadFailed")))
    );
  }, [loadStats, t]);

  useEffect(() => {
    if (tab === "cache") {
      void loadCache().catch((error) =>
        toast.error(errorMessage(error, t("toasts.loadFailed")))
      );
    }
    if (tab === "calls") {
      void loadCalls().catch((error) =>
        toast.error(errorMessage(error, t("toasts.loadFailed")))
      );
    }
  }, [tab, loadCache, loadCalls, t]);

  async function handleToggle(enabled: boolean) {
    try {
      await updateAdminSettings({ mcp_gateway_enabled: enabled });
      await mutate(SWR_KEYS.settings);
      toast.success(t("toasts.updated"));
    } catch (error) {
      toast.error(errorMessage(error, t("module.description")));
    }
  }

  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header
        icon={route.icon}
        title={t("header.title")}
        description={t("header.description")}
        divider
      />
      <SettingsLayouts.Body>
        <div className="flex flex-col gap-6">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex flex-col gap-1">
              <Text as="p" mainUiMuted>
                {t("module.label")}
              </Text>
              <Text as="p" secondaryBody text03>
                {t("module.description")}
              </Text>
              {stats?.retention_days ? (
                <Text as="p" secondaryBody text03>
                  {t("module.retention", { days: stats.retention_days })}
                </Text>
              ) : null}
            </div>
            <Switch
              checked={settings.mcp_gateway_enabled === true}
              onCheckedChange={(checked) => void handleToggle(checked)}
            />
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <InputSelect
              value={selectedSlug || "__all__"}
              onValueChange={(value) =>
                setQuery({ server: value === "__all__" ? null : value })
              }
            >
              <InputSelect.Trigger />
              <InputSelect.Content>
                <InputSelect.Item value="__all__">
                  {t("filter.all")}
                </InputSelect.Item>
                {boundServers.map((server) => (
                  <InputSelect.Item
                    key={server.id}
                    value={server.catalog_slug ?? ""}
                  >
                    {server.name}
                  </InputSelect.Item>
                ))}
              </InputSelect.Content>
            </InputSelect>
            <InputSelect
              value={windowKind}
              onValueChange={(value) => {
                if (value === "24h" || value === "7d") setWindowKind(value);
              }}
            >
              <InputSelect.Trigger />
              <InputSelect.Content>
                <InputSelect.Item value="24h">
                  {t("window.24h")}
                </InputSelect.Item>
                <InputSelect.Item value="7d">{t("window.7d")}</InputSelect.Item>
              </InputSelect.Content>
            </InputSelect>
            <InputTypeIn
              aria-label={t("filter.toolPlaceholder")}
              placeholder={t("filter.toolPlaceholder")}
              value={toolFilter}
              onChange={(event) => setToolFilter(event.target.value)}
            />
          </div>

          {boundServers.length === 0 ? (
            <div className="flex flex-col gap-3">
              <Text as="p">{t("emptyBound")}</Text>
              <Button
                href={ADMIN_ROUTES.MCP_ACTIONS.path}
                prominence="secondary"
              >
                {t("openActions")}
              </Button>
            </div>
          ) : null}

          <Tabs value={tab} onValueChange={(value) => setQuery({ tab: value })}>
            <Tabs.List>
              <Tabs.Trigger value="overview">{t("tabs.overview")}</Tabs.Trigger>
              <Tabs.Trigger value="cache">{t("tabs.cache")}</Tabs.Trigger>
              <Tabs.Trigger value="calls">{t("tabs.calls")}</Tabs.Trigger>
            </Tabs.List>
            <Tabs.Content value="overview">
              {stats ? (
                <div className="grid grid-cols-2 gap-4 pt-4 md:grid-cols-3">
                  <Stat
                    label={t("stats.total")}
                    value={String(stats.total_calls)}
                  />
                  <Stat
                    label={t("stats.hitRate")}
                    value={formatPercent(stats.hit_rate)}
                  />
                  <Stat
                    label={t("stats.billed")}
                    value={String(stats.upstream_billed)}
                  />
                  <Stat
                    label={t("stats.saved")}
                    value={String(stats.saved_calls)}
                  />
                  <Stat
                    label={t("storage.stored")}
                    value={formatBytes(stats.blob_total_bytes)}
                  />
                  <Stat
                    label={t("stats.hits")}
                    value={String(stats.cache_hits)}
                  />
                </div>
              ) : null}
            </Tabs.Content>
            <Tabs.Content value="cache">
              <table className="mt-4 w-full text-left text-sm">
                <thead>
                  <tr className="text-text-03">
                    <th className="py-2">{t("cache.title")}</th>
                    <th>{t("filter.title")}</th>
                    <th>{t("cache.hits")}</th>
                    <th>{t("storage.stored")}</th>
                    <th>{t("cache.refresh")}</th>
                  </tr>
                </thead>
                <tbody>
                  {cacheRows.map((row) => (
                    <tr
                      key={row.cache_key}
                      className="border-t border-border-02"
                    >
                      <td className="py-2">{row.effective_tool_name}</td>
                      <td>{row.catalog_slug}</td>
                      <td>{row.hit_count}</td>
                      <td>{formatBytes(row.size_bytes)}</td>
                      <td className="flex gap-2 py-2">
                        <Button
                          prominence="internal"
                          onClick={() =>
                            void invalidateMcpGatewayCache({
                              cache_key: row.cache_key,
                            }).then(() => loadCache())
                          }
                        >
                          {t("cache.invalidate")}
                        </Button>
                        <Button
                          prominence="internal"
                          onClick={() =>
                            void refreshMcpGatewayCache(row.cache_key)
                          }
                        >
                          {t("cache.refresh")}
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {cacheCursor ? (
                <Button
                  prominence="secondary"
                  onClick={() => void loadCache(cacheCursor)}
                >
                  {t("loadMore")}
                </Button>
              ) : null}
            </Tabs.Content>
            <Tabs.Content value="calls">
              <table className="mt-4 w-full text-left text-sm">
                <thead>
                  <tr className="text-text-03">
                    <th className="py-2">{t("window.label")}</th>
                    <th>{t("filter.title")}</th>
                    <th>{t("cache.title")}</th>
                    <th>{t("stats.hits")}</th>
                    <th>{t("storage.transferred")}</th>
                  </tr>
                </thead>
                <tbody>
                  {callRows.map((row) => (
                    <tr key={row.id} className="border-t border-border-02">
                      <td className="py-2">
                        {new Date(row.created_at).toLocaleString()}
                      </td>
                      <td>{row.catalog_slug}</td>
                      <td>{row.effective_tool_name}</td>
                      <td>{row.outcome}</td>
                      <td>{row.arguments_preview}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {callCursor ? (
                <Button
                  prominence="secondary"
                  onClick={() => void loadCalls(callCursor)}
                >
                  {t("loadMore")}
                </Button>
              ) : null}
            </Tabs.Content>
          </Tabs>
        </div>
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-12 border border-border-02 p-4">
      <Text as="p" secondaryBody text03>
        {label}
      </Text>
      <Text as="p" headingH3>
        {value}
      </Text>
    </div>
  );
}
