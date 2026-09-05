"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import useSWR, { mutate } from "swr";
import { Button, InputTypeIn, Switch, Text } from "@opal/components";
import { SettingsLayouts, toast } from "@opal/layouts";
import { SvgMcp, SvgPlus, SvgTrash } from "@opal/icons";
import {
  createMcpCatalogEntry,
  deleteMcpCatalogEntry,
  listMcpCatalogEntries,
  listMcpPacks,
  refreshMcpCatalogEntryTools,
  updateMcpCatalogEntry,
} from "@/lib/mcp-catalog/api";
import type { McpCatalogEntry, McpPack } from "@/lib/mcp-catalog/types";
import { McpCatalogOrigin } from "@/lib/mcp-catalog/types";
import { errorHandlingFetcher } from "@/lib/fetcher";
import { SWR_KEYS } from "@/lib/swr-keys";
import { useSettings } from "@/lib/settings/hooks";
import { updateAdminSettings } from "@/lib/settings/svc";
import { toSettings } from "@/lib/settings/types";
import { ADMIN_ROUTES } from "@/lib/admin-routes";

const route = ADMIN_ROUTES.MCP_CATALOG;

function toCatalogSlug(raw: string): string {
  return raw
    .trim()
    .toLowerCase()
    .replace(/^@/, "")
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/^[-_]+|[-_]+$/g, "")
    .slice(0, 128);
}

interface UserGroupOption {
  id: number;
  name: string;
}

function errorMessage(error: Error | unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

export default function McpCatalogPage() {
  const t = useTranslations("admin.mcpCatalog");
  const settings = useSettings();

  const [packs, setPacks] = useState<McpPack[]>([]);
  const [entries, setEntries] = useState<McpCatalogEntry[]>([]);
  const [packSlug, setPackSlug] = useState("");
  const [slug, setSlug] = useState("");
  const [upstreamUrl, setUpstreamUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [installPublic, setInstallPublic] = useState(true);
  const [installing, setInstalling] = useState(false);
  const [savingModule, setSavingModule] = useState(false);

  const { data: groups } = useSWR<UserGroupOption[]>(
    SWR_KEYS.shareableGroups,
    errorHandlingFetcher
  );

  const selectedPack = useMemo(
    () => packs.find((pack) => pack.slug === packSlug) ?? null,
    [packs, packSlug]
  );

  const loadEntries = useCallback(async () => {
    setEntries(await listMcpCatalogEntries());
  }, []);

  useEffect(() => {
    void Promise.all([listMcpPacks(), loadEntries()])
      .then(([packRows]) => {
        setPacks(packRows);
        setPackSlug((current) => current || packRows[0]?.slug || "");
      })
      .catch((error) =>
        toast.error(errorMessage(error, t("toasts.loadFailed")))
      );
  }, [loadEntries, t]);

  useEffect(() => {
    if (selectedPack) {
      setUpstreamUrl(selectedPack.default_upstream_url);
    }
  }, [selectedPack]);

  async function handleInstall() {
    const trimmedSlug = toCatalogSlug(slug);
    const trimmedUrl = upstreamUrl.trim();
    if (!trimmedSlug || !packSlug || !trimmedUrl) {
      toast.error(t("toasts.installFailed"));
      return;
    }
    setInstalling(true);
    try {
      const entry = await createMcpCatalogEntry({
        slug: trimmedSlug,
        display_name: slug.trim() || trimmedSlug,
        pack_slug: packSlug,
        upstream_url: trimmedUrl,
        credentials: apiKey.trim() ? { api_key: apiKey.trim() } : {},
        enabled: true,
        is_public: installPublic,
        group_ids: [],
      });
      setSlug("");
      setApiKey("");
      await loadEntries();
      if (entry.discovery_error) {
        toast.error(
          t("installed.discoveryError", { error: entry.discovery_error })
        );
      } else {
        toast.success(t("toasts.installed"));
      }
    } catch (error) {
      toast.error(errorMessage(error, t("toasts.installFailed")));
    } finally {
      setInstalling(false);
    }
  }

  async function handleRefreshTools(entry: McpCatalogEntry) {
    try {
      const updated = await refreshMcpCatalogEntryTools(entry.id);
      await loadEntries();
      if (updated.discovery_error) {
        toast.error(
          t("installed.discoveryError", { error: updated.discovery_error })
        );
        return;
      }
      toast.success(t("toasts.refreshed"));
    } catch (error) {
      toast.error(errorMessage(error, t("toasts.refreshFailed")));
    }
  }

  async function handlePatch(
    entry: McpCatalogEntry,
    patch: Parameters<typeof updateMcpCatalogEntry>[1]
  ) {
    try {
      await updateMcpCatalogEntry(entry.id, patch);
      await loadEntries();
    } catch (error) {
      toast.error(errorMessage(error, t("toasts.updateFailed")));
    }
  }

  async function handleDelete(entry: McpCatalogEntry) {
    try {
      await deleteMcpCatalogEntry(entry.id);
      await loadEntries();
      toast.success(t("toasts.removed"));
    } catch (error) {
      toast.error(errorMessage(error, t("toasts.removeFailed")));
    }
  }

  function toggleGroup(entry: McpCatalogEntry, groupId: number) {
    const next = entry.group_ids.includes(groupId)
      ? entry.group_ids.filter((id) => id !== groupId)
      : [...entry.group_ids, groupId];
    void handlePatch(entry, { group_ids: next });
  }

  async function handleModuleToggle(checked: boolean) {
    if (!settings) return;
    setSavingModule(true);
    try {
      await updateAdminSettings({
        ...toSettings(settings),
        mcp_gateway_enabled: checked,
      });
      await mutate(SWR_KEYS.settings);
      toast.success(checked ? t("module.enabled") : t("module.disabled"));
    } catch (error) {
      toast.error(errorMessage(error, t("module.saveFailed")));
    } finally {
      setSavingModule(false);
    }
  }

  const moduleAvailable = settings?.mcp_gateway_available === true;
  const moduleEnabled = settings?.mcp_gateway_enabled === true;

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
            <Text>{t("module.title")}</Text>
            <Text color="text-02">
              {moduleAvailable ? t("module.description") : t("notDeployed")}
            </Text>
            <div className="flex items-center gap-2">
              <Switch
                data-testid="mcp-module-toggle"
                checked={moduleEnabled}
                disabled={!moduleAvailable || savingModule}
                onCheckedChange={(checked) => void handleModuleToggle(checked)}
                aria-label={t("module.title")}
              />
              <Text color="text-02">{t("module.label")}</Text>
            </div>
          </section>

          <section className="flex flex-col gap-3">
            <Text>{t("install.title")}</Text>
            <Text color="text-02">{t("install.description")}</Text>
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
            <InputTypeIn
              value={slug}
              onChange={(event) => setSlug(event.target.value)}
              placeholder={t("install.slug")}
              aria-label={t("install.slug")}
            />
            <Text color="text-02">{t("install.slugHint")}</Text>
            <InputTypeIn
              value={upstreamUrl}
              onChange={(event) => setUpstreamUrl(event.target.value)}
              placeholder={t("install.upstreamUrl")}
              aria-label={t("install.upstreamUrl")}
            />
            <InputTypeIn
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              placeholder={t("install.apiKey")}
              aria-label={t("install.apiKey")}
            />
            <div className="flex items-center gap-2">
              <Switch
                checked={installPublic}
                onCheckedChange={setInstallPublic}
                aria-label={t("access.public")}
              />
              <Text color="text-02">{t("access.public")}</Text>
            </div>
            <Button
              icon={SvgPlus}
              onClick={() => void handleInstall()}
              disabled={installing}
            >
              {t("install.submit")}
            </Button>
          </section>

          <section className="flex flex-col gap-3">
            <Text>{t("installed.title")}</Text>
            {entries.length === 0 ? (
              <Text color="text-02">{t("installed.empty")}</Text>
            ) : (
              entries.map((entry) => (
                <div
                  key={entry.id}
                  data-testid={`mcp-catalog-entry-${entry.slug}`}
                  className="flex flex-col gap-3 rounded-lg border border-border-02 p-3"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex flex-col">
                      <Text>{entry.display_name}</Text>
                      <Text color="text-02">{entry.gateway_url}</Text>
                      <Text color="text-02">
                        {t("installed.toolCount", { count: entry.tool_count })}
                      </Text>
                      {entry.discovery_error && (
                        <Text color="text-02">
                          {t("installed.discoveryError", {
                            error: entry.discovery_error,
                          })}
                        </Text>
                      )}
                    </div>
                    <div className="flex items-center gap-3">
                      <Button
                        prominence="secondary"
                        onClick={() => void handleRefreshTools(entry)}
                      >
                        {t("installed.refreshTools")}
                      </Button>
                      <Switch
                        checked={entry.enabled}
                        onCheckedChange={(checked) =>
                          void handlePatch(entry, { enabled: checked })
                        }
                        aria-label={t("installed.enabled")}
                      />
                      <Button
                        icon={SvgTrash}
                        variant="danger"
                        prominence="tertiary"
                        onClick={() => void handleDelete(entry)}
                        aria-label={t("installed.remove")}
                      />
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <Switch
                      data-testid={`mcp-catalog-public-${entry.slug}`}
                      checked={entry.is_public}
                      onCheckedChange={(checked) =>
                        void handlePatch(entry, { is_public: checked })
                      }
                      aria-label={t("access.public")}
                    />
                    <Text color="text-02">{t("access.public")}</Text>
                  </div>

                  {!entry.is_public && (
                    <div className="flex flex-col gap-2">
                      <Text color="text-02">{t("access.groups")}</Text>
                      <div className="flex flex-wrap gap-2">
                        {(groups ?? []).map((group) => (
                          <Button
                            key={group.id}
                            prominence={
                              entry.group_ids.includes(group.id)
                                ? "primary"
                                : "secondary"
                            }
                            disabled={entry.origin === McpCatalogOrigin.PUSHED}
                            onClick={() => toggleGroup(entry, group.id)}
                          >
                            {group.name}
                          </Button>
                        ))}
                      </div>
                      {(groups ?? []).length === 0 && (
                        <Text color="text-02">{t("access.noGroups")}</Text>
                      )}
                    </div>
                  )}
                </div>
              ))
            )}
          </section>
        </div>
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
