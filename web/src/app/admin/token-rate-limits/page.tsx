"use client";

import { SettingsLayouts } from "@opal/layouts";
import { useAdminRouteTitle } from "@/lib/adminNavLabels";
import { ADMIN_ROUTES } from "@/lib/admin-routes";
import TokenRateLimitsPanel from "./TokenRateLimitsPanel";

export default function TokenRateLimitsPage() {
  const adminRouteTitle = useAdminRouteTitle();
  const route = ADMIN_ROUTES.TOKEN_RATE_LIMITS;
  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header
        icon={route.icon}
        title={adminRouteTitle(route)}
        divider
      />
      <SettingsLayouts.Body>
        <TokenRateLimitsPanel />
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
