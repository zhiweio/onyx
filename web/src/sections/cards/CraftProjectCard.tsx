"use client";

import { useCallback, type MouseEvent } from "react";
import { useFormatter, useTranslations } from "next-intl";
import { Button } from "@opal/components";
import { Content } from "@opal/layouts";
import { SvgFolder, SvgPlayCircle, SvgTrash } from "@opal/icons";
import { CardItemLayout } from "@/layouts/general-layouts";
import { Interactive } from "@opal/core";
import { Card } from "@/refresh-components/cards";
import type { CraftProject } from "@/lib/craft-projects/types";

export interface CraftProjectCardProps {
  project: CraftProject;
  onClick?: (project: CraftProject) => void;
  onContinue?: (project: CraftProject) => void;
  onDelete?: (project: CraftProject) => void;
  continuePending?: boolean;
}

function stopAndCall(
  event: MouseEvent<HTMLElement>,
  handler: ((project: CraftProject) => void) | undefined,
  project: CraftProject
) {
  event.stopPropagation();
  handler?.(project);
}

export default function CraftProjectCard({
  project,
  onClick,
  onContinue,
  onDelete,
  continuePending = false,
}: CraftProjectCardProps) {
  const t = useTranslations("craft.projects");
  const format = useFormatter();
  const hasChats = project.session_count > 0;
  const lastActivity = format.relativeTime(new Date(project.updated_at));

  const handleClick = useCallback(() => {
    onClick?.(project);
  }, [onClick, project]);

  return (
    <Interactive.Simple onClick={handleClick} group="group/CraftProjectCard">
      <Card variant="primary" padding={0} gap={0} height="full">
        <div className="flex self-stretch min-h-24">
          <CardItemLayout
            icon={SvgFolder}
            title={project.name}
            description={project.description || undefined}
          />
        </div>
        <div className="bg-background-tint-01 p-1.5 flex flex-row items-center justify-between w-full">
          <div className="py-1 px-1 min-w-0 flex-1">
            <Content
              icon={SvgFolder}
              title={`${t("card.fileCount.label", {
                count: project.file_count,
              })} · ${t("card.sessionCount.label", {
                count: project.session_count,
              })} · ${t("card.lastActivity.label", { time: lastActivity })}`}
              sizePreset="secondary"
              variant="body"
              color="muted"
            />
          </div>
          <div className="flex items-center gap-1">
            <div className="opacity-0 transition-opacity group-hover/CraftProjectCard:opacity-100 group-focus-within/CraftProjectCard:opacity-100 no-hover:opacity-100">
              <Button
                prominence="tertiary"
                size="sm"
                icon={SvgTrash}
                tooltip={t("card.delete.tooltip")}
                aria-label={t("card.delete.tooltip")}
                onClick={(event) => stopAndCall(event, onDelete, project)}
              />
            </div>
            <Button
              prominence="primary"
              size="sm"
              icon={SvgPlayCircle}
              disabled={continuePending}
              onClick={(event) => stopAndCall(event, onContinue, project)}
            >
              {hasChats
                ? t("card.continue.label")
                : t("detail.startChat.label")}
            </Button>
          </div>
        </div>
      </Card>
    </Interactive.Simple>
  );
}
