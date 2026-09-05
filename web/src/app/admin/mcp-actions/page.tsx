"use client";

import MCPPageContent from "@/sections/actions/MCPPageContent";
import { useAdminRouteTitle } from "@/lib/adminNavLabels";
import { useTranslations } from "next-intl";
import { Button } from "@opal/components";
import { SettingsLayouts } from "@opal/layouts";
import { ADMIN_ROUTES } from "@/lib/admin-routes";

const route = ADMIN_ROUTES.MCP_ACTIONS;

export default function Main() {
  const t = useTranslations("admin.mcpActions");
  const adminRouteTitle = useAdminRouteTitle();

  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header
        icon={route.icon}
        title={adminRouteTitle(route)}
        description={t("header.description")}
        rightChildren={
          <Button
            href={ADMIN_ROUTES.MCP_GATEWAY.path}
            prominence="secondary"
          >
            {t("header.gatewayLink")}
          </Button>
        }
        divider
      />
      <SettingsLayouts.Body>
        <MCPPageContent />
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
