"use client";

import { useState } from "react";
import { useFormatter, useTranslations } from "next-intl";
import { Button, Card, Checkbox, Tag, Text, type TagColor } from "@opal/components";
import { ConfirmationModalLayout, ContentAction } from "@opal/layouts";
import { SvgRefreshCw, SvgServer, SvgSimpleLoader } from "@opal/icons";
import { Section } from "@/layouts/general-layouts";
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
  const liveStatus = projectSandboxStatus(sandbox);
  const status: CraftProjectSandboxStatusKey = resetting
    ? "provisioning"
    : liveStatus;
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [migrateOutputs, setMigrateOutputs] = useState(false);
  const heartbeat = sandbox?.last_heartbeat
    ? format.relativeTime(new Date(sandbox.last_heartbeat))
    : null;
  const progressDescription = migrateOutputs
    ? t("reset.progress.migrateDescription")
    : t("reset.progress.description");
  const description = resetting
    ? progressDescription
    : heartbeat
      ? `${t(`description.${status}`)} · ${t("lastHeartbeat", { time: heartbeat })}`
      : t(`description.${status}`);
  const resetDisabled = resetting || liveStatus === "provisioning";

  function openConfirm() {
    if (resetDisabled) return;
    setMigrateOutputs(false);
    setConfirmOpen(true);
  }

  function closeConfirm() {
    setConfirmOpen(false);
  }

  function handleConfirmReset() {
    setConfirmOpen(false);
    void onReset(migrateOutputs);
  }

  return (
    <>
      <Card
        border="solid"
        rounding={4}
        padding={4}
        data-testid="craft-project-sandbox"
      >
        <Section
          gap={3}
          alignItems="stretch"
          justifyContent="start"
          height="auto"
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
                  icon={resetting ? SvgSimpleLoader : SvgRefreshCw}
                  disabled={resetDisabled}
                  onClick={openConfirm}
                >
                  {resetting ? t("reset.progress.label") : t("reset.label")}
                </Button>
                <Tag
                  color={SANDBOX_STATUS_COLOR[status]}
                  title={
                    resetting
                      ? t("reset.progress.label")
                      : t(`status.${status}`)
                  }
                />
              </div>
            }
          />
          {resetting && (
            <div
              className="flex items-center gap-2 rounded-12 border border-border-01 bg-background-neutral-00 px-3 py-2"
              data-testid="craft-project-sandbox-progress"
              role="status"
              aria-live="polite"
            >
              <span
                className="h-2 w-2 shrink-0 rounded-full bg-status-warning-05 animate-pulse"
                aria-hidden
              />
              <Text font="main-ui-body" color="text-05">
                {progressDescription}
              </Text>
            </div>
          )}
        </Section>
      </Card>

      {confirmOpen && (
        <ConfirmationModalLayout
          icon={SvgRefreshCw}
          title={t("reset.title")}
          description={t("reset.description")}
          onClose={closeConfirm}
          hideCancel
          submit={
            <>
              <Button prominence="secondary" onClick={closeConfirm}>
                {t("reset.cancel.label")}
              </Button>
              <Button variant="danger" onClick={handleConfirmReset}>
                {t("reset.confirm.label")}
              </Button>
            </>
          }
        >
          <label className="flex items-start gap-2">
            <Checkbox
              checked={migrateOutputs}
              aria-label={t("reset.migrateOutputs.label")}
              onCheckedChange={setMigrateOutputs}
            />
            <div className="flex min-w-0 flex-col gap-1">
              <Text font="main-ui-body">{t("reset.migrateOutputs.label")}</Text>
              <Text font="secondary-body" color="text-03">
                {t("reset.migrateOutputs.description")}
              </Text>
            </div>
          </label>
        </ConfirmationModalLayout>
      )}
    </>
  );
}
