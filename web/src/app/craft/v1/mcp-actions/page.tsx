"use client";

import { useState } from "react";
import MCPPageContent from "@/sections/actions/MCPPageContent";
import { useTranslations } from "next-intl";
import { Tabs } from "@opal/components";
import { SettingsLayouts } from "@opal/layouts";
import { SvgMcp } from "@opal/icons";
import type { GalleryTab } from "@/lib/system-catalog/useGalleryTab";

export default function CraftMcpActionsPage() {
  const t = useTranslations("craft.mcpActions");
  const tGallery = useTranslations("craft.gallery");
  const [tab, setTab] = useState<GalleryTab>("mine");

  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header
        icon={SvgMcp}
        title={t("header.title")}
        description={t("header.description")}
      >
        <Tabs
          value={tab}
          onValueChange={(value) => setTab(value as GalleryTab)}
        >
          <Tabs.List>
            <Tabs.Trigger value="mine" data-testid="GalleryTabs/mine">
              {tGallery("tabs.mine.label")}
            </Tabs.Trigger>
            <Tabs.Trigger value="gallery" data-testid="GalleryTabs/gallery">
              {tGallery("tabs.gallery.label")}
            </Tabs.Trigger>
          </Tabs.List>
        </Tabs>
      </SettingsLayouts.Header>
      <SettingsLayouts.Body>
        <MCPPageContent
          key={tab}
          variant={tab === "mine" ? "personal" : "gallery"}
        />
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
