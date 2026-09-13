"use client";

import { useFormatter, useTranslations } from "next-intl";
import { Card, Tag, type TagColor } from "@opal/components";
import { ContentAction } from "@opal/layouts";
import { SvgServer } from "@opal/icons";
import type { CraftProjectSandbox } from "@/lib/craft-projects/types";
import {
  projectSandboxStatus,
  type CraftProjectSandboxStatusKey,
} from "@/lib/craft-projects/display";

const SANDBOX_STATUS_COLOR: Record<CraftProjectSandboxStatusKey, TagColor> = {
  running: "green",
  provisioning: "amber",
  sleeping: "blue",
  terminated: "gray",
  failed: "red",
  missing: "gray",
};

interface CraftProjectSandboxCardProps {
  sandbox: CraftProjectSandbox | null | undefined;
}

export default function CraftProjectSandboxCard({
  sandbox,
}: CraftProjectSandboxCardProps) {
  const t = useTranslations("craft.projects.detail.sandbox");
  const format = useFormatter();
  const status = projectSandboxStatus(sandbox);
  const heartbeat = sandbox?.last_heartbeat
    ? format.relativeTime(new Date(sandbox.last_heartbeat))
    : null;
  const description = heartbeat
    ? `${t(`description.${status}`)} · ${t("lastHeartbeat", { time: heartbeat })}`
    : t(`description.${status}`);

  return (
    <Card
      border="solid"
      rounding={4}
      padding={4}
      data-testid="craft-project-sandbox"
    >
      <ContentAction
        icon={SvgServer}
        title={t("title")}
        description={description}
        sizePreset="main-ui"
        variant="section"
        width="full"
        rightChildren={
          <Tag
            color={SANDBOX_STATUS_COLOR[status]}
            title={t(`status.${status}`)}
          />
        }
      />
    </Card>
  );
}
