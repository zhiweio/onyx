"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Switch, Text } from "@opal/components";
import { Content, ContentAction, toast } from "@opal/layouts";
import { SvgMcp } from "@opal/icons";
import Card from "@/refresh-components/cards/Card";
import { Section } from "@/layouts/general-layouts";
import {
  listSystemMcpServers,
  setSystemMcpServerEnabled,
} from "@/lib/mcp-catalog/api";
import type { SystemMcpServer } from "@/lib/mcp-catalog/types";
import { useSettings } from "@/lib/settings/hooks";

/**
 * The system MCP servers an admin granted to one of this user's groups.
 *
 * Being granted a server does not switch it on: the toggle here is the user's
 * own choice, so a new grant never quietly adds tools to their chat. The whole
 * section disappears when the gateway module is off.
 */
export default function SystemMcpSettings() {
  const t = useTranslations("settings.systemMcp");
  const settings = useSettings();
  const [servers, setServers] = useState<SystemMcpServer[] | null>(null);

  const gatewayEnabled = settings?.mcp_gateway_enabled === true;

  const load = useCallback(async () => {
    try {
      setServers(await listSystemMcpServers());
    } catch {
      setServers([]);
    }
  }, []);

  useEffect(() => {
    if (!gatewayEnabled) {
      setServers([]);
      return;
    }
    void load();
  }, [gatewayEnabled, load]);

  async function handleToggle(server: SystemMcpServer, enabled: boolean) {
    // Move the switch first so it does not lag the click, then reconcile with
    // whatever the server actually stored.
    setServers(
      (current) =>
        current?.map((item) =>
          item.mcp_server_id === server.mcp_server_id
            ? { ...item, enabled_for_user: enabled }
            : item
        ) ?? null
    );
    try {
      await setSystemMcpServerEnabled(server.mcp_server_id, enabled);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("toggleFailed"));
    } finally {
      await load();
    }
  }

  if (!gatewayEnabled || servers === null || servers.length === 0) {
    return null;
  }

  return (
    <Section gap={3} justifyContent="start">
      <Content
        title={t("title")}
        description={t("description")}
        sizePreset="main-content"
        variant="section"
        width="full"
      />
      {servers.map((server) => (
        <Card
          key={server.mcp_server_id}
          data-testid={`system-mcp-${server.catalog_slug}`}
        >
          <ContentAction
            icon={SvgMcp}
            sizePreset="main-ui"
            variant="section"
            title={server.display_name}
            description={
              server.description ?? t("toolCount", { count: server.tool_count })
            }
            rightChildren={
              <Switch
                data-testid={`system-mcp-toggle-${server.catalog_slug}`}
                checked={server.enabled_for_user}
                onCheckedChange={(checked) =>
                  void handleToggle(server, checked)
                }
                aria-label={t("toggleLabel", { name: server.display_name })}
              />
            }
          />
        </Card>
      ))}
      {servers.length === 0 && <Text color="text-02">{t("empty")}</Text>}
    </Section>
  );
}
