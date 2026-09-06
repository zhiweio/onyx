"use client";

import MCPPageContent from "@/sections/actions/MCPPageContent";
import { useAdminRouteTitle } from "@/lib/adminNavLabels";
import { useTranslations } from "next-intl";
import { Button } from "@opal/components";
import Text from "@/refresh-components/texts/Text";
import { SettingsLayouts } from "@opal/layouts";
import { ADMIN_ROUTES } from "@/lib/admin-routes";
import { useSettings } from "@/lib/settings/hooks";

const route = ADMIN_ROUTES.MCP_ACTIONS;

export default function Main() {
  const t = useTranslations("admin.mcpActions");
  const adminRouteTitle = useAdminRouteTitle();
  const settings = useSettings();
  const gatewayAvailable = settings.mcp_gateway_available === true;
  const gatewayOn = gatewayAvailable && settings.mcp_gateway_enabled === true;

  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header
        icon={route.icon}
        title={adminRouteTitle(route)}
        description={t("header.description")}
        rightChildren={
          gatewayAvailable ? (
            <div className="flex items-center gap-2">
              <Text as="p" secondaryBody text03>
                {gatewayOn ? t("header.gatewayOn") : t("header.gatewayOff")}
              </Text>
              <Button
                href={ADMIN_ROUTES.MCP_GATEWAY.path}
                prominence="secondary"
              >
                {t("header.gatewayLink")}
              </Button>
            </div>
          ) : undefined
        }
        divider
      />
      <SettingsLayouts.Body>
        <MCPPageContent />
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
