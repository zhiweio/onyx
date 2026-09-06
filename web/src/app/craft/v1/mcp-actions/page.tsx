"use client";

import MCPPageContent from "@/sections/actions/MCPPageContent";
import { useTranslations } from "next-intl";
import { SettingsLayouts } from "@opal/layouts";
import { SvgMcp } from "@opal/icons";

export default function CraftMcpActionsPage() {
  const t = useTranslations("craft.mcpActions");

  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header
        icon={SvgMcp}
        title={t("header.title")}
        description={t("header.description")}
        divider
      />
      <SettingsLayouts.Body>
        <MCPPageContent variant="personal" />
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
