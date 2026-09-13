"use client";

import { useState } from "react";
import { useFormatter, useTranslations } from "next-intl";
import { Button, Card, Checkbox, Tag, Text, type TagColor } from "@opal/components";
import { ConfirmationModalLayout, ContentAction } from "@opal/layouts";
import { SvgRefreshCw, SvgServer } from "@opal/icons";
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
  resetting?: boolean;
  onReset: (migrateOutputs: boolean) => Promise<void> | void;
}

export default function CraftProjectSandboxCard({
  sandbox,
  resetting = false,
  onReset,
}: CraftProjectSandboxCardProps) {
  const t = useTranslations("craft.projects.detail.sandbox");
  const format = useFormatter();
  const status = projectSandboxStatus(sandbox);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [migrateOutputs, setMigrateOutputs] = useState(false);
  const heartbeat = sandbox?.last_heartbeat
    ? format.relativeTime(new Date(sandbox.last_heartbeat))
    : null;
  const description = heartbeat
    ? `${t(`description.${status}`)} · ${t("lastHeartbeat", { time: heartbeat })}`
    : t(`description.${status}`);
  const resetDisabled = resetting || status === "provisioning";

  function openConfirm() {
    setMigrateOutputs(false);
    setConfirmOpen(true);
  }

  async function handleConfirmReset() {
    await onReset(migrateOutputs);
    setConfirmOpen(false);
  }

  return (
    <>
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
            <div className="flex items-center gap-2">
              <Button
                prominence="tertiary"
                size="sm"
                icon={SvgRefreshCw}
                disabled={resetDisabled}
                onClick={openConfirm}
              >
                {t("reset.label")}
              </Button>
              <Tag
                color={SANDBOX_STATUS_COLOR[status]}
                title={t(`status.${status}`)}
              />
            </div>
          }
        />
      </Card>

      {confirmOpen && (
        <ConfirmationModalLayout
          icon={SvgRefreshCw}
          title={t("reset.title")}
          description={t("reset.description")}
          onClose={resetting ? undefined : () => setConfirmOpen(false)}
          submit={
            <Button
              disabled={resetting}
              onClick={() => void handleConfirmReset()}
            >
              {t("reset.confirm.label")}
            </Button>
          }
        >
          <label className="flex items-start gap-2">
            <Checkbox
              checked={migrateOutputs}
              disabled={resetting}
              aria-label={t("reset.migrateOutputs.label")}
              onCheckedChange={setMigrateOutputs}
            />
            <Text font="main-ui-body">{t("reset.migrateOutputs.label")}</Text>
          </label>
        </ConfirmationModalLayout>
      )}
    </>
  );
}
