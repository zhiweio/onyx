"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Button, Switch, Tag } from "@opal/components";
import { Hoverable } from "@opal/core";
import { toast } from "@opal/layouts";
import { SvgEdit } from "@opal/icons";
import McpToolsCard from "@/sections/actions/McpToolsCard";
import type { MCPServer } from "@/lib/tools/types";
import type { ConfiguredIntegration } from "@/views/admin/ExternalAppsPage/interfaces";

/**
 * The MCP row on the craft apps admin page: the shared expandable tools
 * card (chat-preferences design) carrying the integration controls —
 * craft availability switch and the policy edit action — in its header.
 */
export default function McpIntegrationCard({
  integration,
  server,
}: {
  integration: ConfiguredIntegration;
  server: MCPServer;
}) {
  const t = useTranslations("admin.externalApps");
  const [isMutating, setIsMutating] = useState(false);

  const toggle = async () => {
    setIsMutating(true);
    try {
      await integration.toggleEnabled();
    } catch (e) {
      toast.error(
        e instanceof Error
          ? e.message
          : integration.enabled
            ? t("card.toasts.disableFailed", { name: integration.name })
            : t("card.toasts.enableFailed", { name: integration.name })
      );
    } finally {
      setIsMutating(false);
    }
  };

  const headerRight = (
    <div className="flex items-center gap-3">
      {integration.warnings.map((warning) => (
        <Tag key={warning} title={warning} color="amber" error />
      ))}
      <Hoverable.Item group="integration-row" variant="appear-on-hover">
        <span className="text-sm text-text-03 whitespace-nowrap">
          {t("card.availableInCraft.label")}
        </span>
      </Hoverable.Item>
      <Switch
        checked={integration.enabled}
        onCheckedChange={() => void toggle()}
        disabled={isMutating}
        aria-label={
          integration.enabled
            ? t("card.toggle.disableAriaLabel", { name: integration.name })
            : t("card.toggle.enableAriaLabel", { name: integration.name })
        }
      />
      {integration.edit && (
        <Button
          prominence="tertiary"
          icon={SvgEdit}
          disabled={isMutating}
          onClick={integration.edit}
          aria-label={t("card.editAction.label")}
        />
      )}
    </div>
  );

  return (
    <Hoverable.Root group="integration-row">
      <McpToolsCard
        name={integration.name}
        description={integration.facts.join(" · ")}
        logo={integration.logo}
        server={server}
        surface="admin"
        headerRight={headerRight}
      />
    </Hoverable.Root>
  );
}
