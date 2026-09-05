"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { Button, InputTypeIn, Text } from "@opal/components";
import { SettingsLayouts, toast } from "@opal/layouts";
import { SvgMcp, SvgPlus } from "@opal/icons";
import {
  createMcpGatewayProvider,
  getMcpGatewayStats,
  invalidateMcpGatewayCache,
  listMcpGatewayCache,
  listMcpGatewayPacks,
  listMcpGatewayPolicies,
  listMcpGatewayProviders,
  refreshMcpGatewayCache,
} from "@/lib/mcp-gateway/api";
import type {
  McpGatewayCacheEntry,
  McpGatewayPack,
  McpGatewayPolicy,
  McpGatewayProvider,
  McpGatewayStats,
} from "@/lib/mcp-gateway/types";
import { ADMIN_ROUTES } from "@/lib/admin-routes";

const route = ADMIN_ROUTES.MCP_GATEWAY;

function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

export default function McpGatewayPage() {
  const t = useTranslations("admin.mcpGateway");
  const [packs, setPacks] = useState<McpGatewayPack[]>([]);
  const [providers, setProviders] = useState<McpGatewayProvider[]>([]);
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  const [policies, setPolicies] = useState<McpGatewayPolicy[]>([]);
  const [cacheEntries, setCacheEntries] = useState<McpGatewayCacheEntry[]>([]);
  const [stats, setStats] = useState<McpGatewayStats | null>(null);
  const [slug, setSlug] = useState("");
  const [packSlug, setPackSlug] = useState("");
  const [upstreamUrl, setUpstreamUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [creating, setCreating] = useState(false);

  const selectedPack = useMemo(
    () => packs.find((pack) => pack.slug === packSlug) ?? null,
    [packs, packSlug]
  );

  const loadProviders = useCallback(async () => {
    const rows = await listMcpGatewayProviders();
    setProviders(rows);
    setSelectedSlug((current) => current ?? rows[0]?.slug ?? null);
  }, []);

  const loadSelected = useCallback(async (providerSlug: string) => {
    const [policyRows, cacheRows, usage] = await Promise.all([
      listMcpGatewayPolicies(providerSlug),
      listMcpGatewayCache(providerSlug),
      getMcpGatewayStats(providerSlug),
    ]);
    setPolicies(policyRows);
    setCacheEntries(cacheRows);
    setStats(usage);
  }, []);

  useEffect(() => {
    void Promise.all([listMcpGatewayPacks(), loadProviders()]).then(
      ([packRows]) => {
        setPacks(packRows);
        setPackSlug((current) => current || packRows[0]?.slug || "");
        const first = packRows[0];
        if (first) {
          setUpstreamUrl((current) => current || first.default_upstream_url);
        }
      }
    );
  }, [loadProviders]);

  useEffect(() => {
    if (!selectedSlug) {
      setPolicies([]);
      setCacheEntries([]);
      setStats(null);
      return;
    }
    void loadSelected(selectedSlug);
  }, [selectedSlug, loadSelected]);

  useEffect(() => {
    if (selectedPack) {
      setUpstreamUrl(selectedPack.default_upstream_url);
    }
  }, [selectedPack]);

  async function handleCreate() {
    const trimmedSlug = slug.trim();
    const trimmedUrl = upstreamUrl.trim();
    if (!trimmedSlug || !packSlug || !trimmedUrl) {
      toast.error(t("toasts.createFailed"));
      return;
    }
    setCreating(true);
    try {
      const created = await createMcpGatewayProvider({
        slug: trimmedSlug,
        pack_slug: packSlug,
        upstream_url: trimmedUrl,
        credentials: apiKey.trim() ? { api_key: apiKey.trim() } : {},
        enabled: true,
        attach_mcp_server: true,
      });
      setSlug("");
      setApiKey("");
      await loadProviders();
      setSelectedSlug(created.slug);
      toast.success(t("toasts.created"));
    } catch (error) {
      console.error(error);
      toast.error(
        error instanceof Error ? error.message : t("toasts.createFailed")
      );
    } finally {
      setCreating(false);
    }
  }

  async function handleInvalidate(cacheKey: string) {
    try {
      await invalidateMcpGatewayCache({ cache_key: cacheKey });
      if (selectedSlug) {
        await loadSelected(selectedSlug);
      }
      toast.success(t("toasts.invalidated"));
    } catch (error) {
      console.error(error);
      toast.error(
        error instanceof Error ? error.message : t("toasts.invalidated")
      );
    }
  }

  async function handleRefresh(cacheKey: string) {
    try {
      await refreshMcpGatewayCache(cacheKey);
      toast.success(t("toasts.refreshed"));
    } catch (error) {
      console.error(error);
      toast.error(
        error instanceof Error ? error.message : t("toasts.refreshed")
      );
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
            <Text>{t("packs.title")}</Text>
            <div className="flex flex-wrap gap-2">
              {packs.map((pack) => (
                <Button
                  key={pack.slug}
                  prominence={pack.slug === packSlug ? "primary" : "secondary"}
                  onClick={() => setPackSlug(pack.slug)}
                >
                  {pack.display_name}
                </Button>
              ))}
            </div>
          </section>

          <section className="flex flex-col gap-3">
            <Text>{t("providers.title")}</Text>
            <InputTypeIn
              value={slug}
              onChange={(event) => setSlug(event.target.value)}
              placeholder={t("providers.slug")}
              aria-label={t("providers.slug")}
            />
            <InputTypeIn
              value={upstreamUrl}
              onChange={(event) => setUpstreamUrl(event.target.value)}
              placeholder={t("providers.upstreamUrl")}
              aria-label={t("providers.upstreamUrl")}
            />
            <InputTypeIn
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              placeholder={t("providers.apiKey")}
              aria-label={t("providers.apiKey")}
            />
            <Button
              icon={SvgPlus}
              onClick={() => void handleCreate()}
              disabled={creating}
            >
              {t("providers.create")}
            </Button>
            {providers.length === 0 ? (
              <Text color="text-02">{t("providers.empty")}</Text>
            ) : (
              <div className="flex flex-col gap-2">
                {providers.map((provider) => (
                  <button
                    key={provider.id}
                    type="button"
                    className="flex items-center justify-between rounded-lg border border-border-02 px-3 py-2 text-left"
                    onClick={() => setSelectedSlug(provider.slug)}
                  >
                    <div>
                      <Text>{provider.display_name}</Text>
                      <Text color="text-02">{provider.gateway_url}</Text>
                    </div>
                    <Text color="text-02">{provider.pack_slug}</Text>
                  </button>
                ))}
              </div>
            )}
          </section>

          {stats && (
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
          )}

          {selectedSlug && (
            <section className="flex flex-col gap-3">
              <Text>{t("policies.title")}</Text>
              {policies.map((policy) => (
                <div
                  key={policy.tool_name}
                  className="flex items-center justify-between rounded-lg border border-border-02 px-3 py-2"
                >
                  <Text>{policy.tool_name}</Text>
                  <Text color="text-02">
                    {`${policy.refresh_mode} · ${t("policies.ttl")} ${policy.ttl_seconds}${
                      policy.is_db_override ? ` · ${t("policies.override")}` : ""
                    }`}
                  </Text>
                </div>
              ))}
            </section>
          )}

          {selectedSlug && (
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
                    <div>
                      <Text>{entry.effective_tool_name}</Text>
                      <Text color="text-02">{String(entry.hit_count)}</Text>
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
          )}
        </div>
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
