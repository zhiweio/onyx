"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { Button, Switch, Tabs } from "@opal/components";
import Text from "@/refresh-components/texts/Text";
import {
  ConfirmationModalLayout,
  InputHorizontal,
  SettingsLayouts,
  toast,
} from "@opal/layouts";
import { getMcpGatewayStats } from "@/lib/mcp-catalog/api";
import type { McpGatewayStats } from "@/lib/mcp-catalog/types";
import { ADMIN_ROUTES } from "@/lib/admin-routes";
import { useAdminMcpServers } from "@/lib/tools/hooks";
import { useSettings } from "@/lib/settings/hooks";
import { updateAdminSettings } from "@/lib/settings/svc";
import { mutate } from "swr";
import { SWR_KEYS } from "@/lib/swr-keys";
import {
  rangeForInclusiveDays,
  type DateRange,
} from "@/refresh-components/DateRangePicker";
import GatewayFilters from "./GatewayFilters";
import GatewayCacheTable from "./GatewayCacheTable";
import GatewayCallsTable from "./GatewayCallsTable";
import { errorMessage, formatBytes, formatPercent } from "./format";
import { useDebouncedValue } from "./useDebouncedValue";

const route = ADMIN_ROUTES.MCP_GATEWAY;

type GatewayTab = "overview" | "cache" | "calls";

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

  const [dateRange, setDateRange] = useState<DateRange>(
    rangeForInclusiveDays(7)
  );
  const [toolFilter, setToolFilter] = useState("");
  const debouncedTool = useDebouncedValue(toolFilter);
  const [stats, setStats] = useState<McpGatewayStats | null>(null);
  const [pendingEnabled, setPendingEnabled] = useState<boolean | null>(null);
  const [isSaving, setIsSaving] = useState(false);

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

  const handleDateRangeChange = useCallback((next: DateRange) => {
    setDateRange(next);
  }, []);

  const handleServerChange = useCallback(
    (slug: string) => {
      setQuery({ server: slug || null });
      setToolFilter("");
    },
    [setQuery]
  );

  useEffect(() => {
    if (!dateRange?.from || !dateRange.to) return;
    void getMcpGatewayStats({
      from: dateRange.from.toISOString(),
      to: dateRange.to.toISOString(),
      catalog_slug: selectedSlug || undefined,
    })
      .then(setStats)
      .catch((error) =>
        toast.error(errorMessage(error, t("toasts.loadFailed")))
      );
  }, [dateRange, selectedSlug, t]);

  async function applyToggle(enabled: boolean) {
    setIsSaving(true);
    try {
      await updateAdminSettings({ mcp_gateway_enabled: enabled });
      await mutate(SWR_KEYS.settings);
      toast.success(t("toasts.updated"));
      setPendingEnabled(null);
    } catch (error) {
      toast.error(errorMessage(error, t("toasts.loadFailed")));
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <SettingsLayouts.Root width="lg" data-testid="mcp-gateway-page">
      <SettingsLayouts.Header
        icon={route.icon}
        title={t("header.title")}
        description={t("header.description")}
        divider
      />
      <SettingsLayouts.Body>
        <div className="flex flex-col gap-6">
          <InputHorizontal
            title={t("module.label")}
            description={t("module.description")}
            withLabel
          >
            <Switch
              checked={settings.mcp_gateway_enabled === true}
              disabled={isSaving}
              onCheckedChange={(checked) => setPendingEnabled(checked)}
              data-testid="mcp-gateway-enable-switch"
            />
          </InputHorizontal>
          {stats ? (
            <Text as="p" secondaryBody text03>
              {stats.retention_days && stats.retention_days > 0
                ? t("module.retention", { days: stats.retention_days })
                : t("module.retentionAll")}
            </Text>
          ) : null}

          <GatewayFilters
            servers={boundServers}
            selectedSlug={selectedSlug}
            onServerChange={handleServerChange}
            selectedTool={toolFilter}
            onToolChange={setToolFilter}
            dateRange={dateRange}
            onDateRangeChange={handleDateRangeChange}
          />

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
              <Tabs.Trigger
                value="overview"
                data-testid="mcp-gateway-tab-overview"
              >
                {t("tabs.overview")}
              </Tabs.Trigger>
              <Tabs.Trigger value="cache" data-testid="mcp-gateway-tab-cache">
                {t("tabs.cache")}
              </Tabs.Trigger>
              <Tabs.Trigger value="calls" data-testid="mcp-gateway-tab-calls">
                {t("tabs.calls")}
              </Tabs.Trigger>
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
              {tab === "cache" ? (
                <GatewayCacheTable
                  catalogSlug={selectedSlug}
                  tool={debouncedTool}
                />
              ) : null}
            </Tabs.Content>
            <Tabs.Content value="calls">
              {tab === "calls" ? (
                <GatewayCallsTable
                  dateRange={dateRange}
                  catalogSlug={selectedSlug}
                  tool={debouncedTool}
                />
              ) : null}
            </Tabs.Content>
          </Tabs>
        </div>
      </SettingsLayouts.Body>

      {pendingEnabled !== null && (
        <ConfirmationModalLayout
          hideCancel
          icon={route.icon}
          title={
            pendingEnabled
              ? t("module.confirmEnableTitle")
              : t("module.confirmDisableTitle")
          }
          onClose={isSaving ? undefined : () => setPendingEnabled(null)}
          submit={
            <>
              <Button
                prominence="secondary"
                disabled={isSaving}
                data-testid="mcp-gateway-confirm-cancel"
                onClick={() => setPendingEnabled(null)}
              >
                {t("module.confirmCancel")}
              </Button>
              <Button
                disabled={isSaving}
                data-testid="mcp-gateway-confirm-toggle"
                onClick={() => {
                  void applyToggle(pendingEnabled);
                }}
              >
                {pendingEnabled
                  ? t("module.confirmEnableAction")
                  : t("module.confirmDisableAction")}
              </Button>
            </>
          }
        >
          <Text as="p" text03>
            {pendingEnabled
              ? t("module.confirmEnableBody")
              : t("module.confirmDisableBody")}
          </Text>
        </ConfirmationModalLayout>
      )}
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
