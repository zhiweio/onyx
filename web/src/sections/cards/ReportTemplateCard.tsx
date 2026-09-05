"use client";

import { useCallback, type MouseEvent } from "react";
import { useTranslations } from "next-intl";
import { Button, Tag } from "@opal/components";
import { Content } from "@opal/layouts";
import { SvgEdit, SvgFileText, SvgTrash } from "@opal/icons";
import { CardItemLayout } from "@/layouts/general-layouts";
import { Interactive } from "@opal/core";
import { Card } from "@/refresh-components/cards";
import {
  canDeleteReportTemplate,
  canEditReportTemplate,
  isWorkspaceReportTemplate,
  type ReportTemplate,
} from "@/lib/report-templates/types";

export interface ReportTemplateCardProps {
  template: ReportTemplate;
  onClick?: (template: ReportTemplate) => void;
  onEdit?: (template: ReportTemplate) => void;
  onDelete?: (template: ReportTemplate) => void;
}

function stopAndCall(
  event: MouseEvent<HTMLElement>,
  handler: ((template: ReportTemplate) => void) | undefined,
  template: ReportTemplate
) {
  event.stopPropagation();
  handler?.(template);
}

export default function ReportTemplateCard({
  template,
  onClick,
  onEdit,
  onDelete,
}: ReportTemplateCardProps) {
  const t = useTranslations("craft.reportTemplates");
  const canEdit = canEditReportTemplate(template);
  const canDelete = canDeleteReportTemplate(template);
  const workspace = isWorkspaceReportTemplate(template);

  const handleClick = useCallback(() => {
    onClick?.(template);
  }, [onClick, template]);

  return (
    <Interactive.Simple onClick={handleClick} group="group/ReportTemplateCard">
      <Card variant="primary" padding={0} gap={0} height="full">
        <div className="flex self-stretch min-h-24">
          <CardItemLayout
            icon={SvgFileText}
            title={template.name}
            description={template.description || template.slug}
          />
        </div>
        <div className="bg-background-tint-01 p-1.5 flex flex-row items-center justify-between w-full">
          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1 px-1 py-1">
            <Tag
              size="sm"
              color={workspace ? "blue" : "purple"}
              title={
                workspace
                  ? t("card.origin.workspace.label")
                  : t("card.origin.personal.label")
              }
            />
            <Content
              title={template.slug}
              sizePreset="secondary"
              variant="body"
              color="muted"
            />
            <Content
              title={t("card.referenced.label", {
                count: template.referenced_count,
              })}
              sizePreset="secondary"
              variant="body"
              color="muted"
            />
          </div>
          <div className="flex items-center gap-1">
            {canEdit && (
              <Button
                prominence="tertiary"
                size="sm"
                icon={SvgEdit}
                tooltip={t("card.edit.tooltip")}
                aria-label={t("card.edit.tooltip")}
                onClick={(event) => stopAndCall(event, onEdit, template)}
              />
            )}
            <Button
              prominence="tertiary"
              size="sm"
              icon={SvgTrash}
              disabled={!canDelete}
              tooltip={
                canDelete
                  ? t("card.delete.tooltip")
                  : t("card.deleteBlocked.tooltip")
              }
              aria-label={
                canDelete
                  ? t("card.delete.tooltip")
                  : t("card.deleteBlocked.tooltip")
              }
              onClick={(event) => {
                if (!canDelete) {
                  event.stopPropagation();
                  return;
                }
                stopAndCall(event, onDelete, template);
              }}
            />
          </div>
        </div>
      </Card>
    </Interactive.Simple>
  );
}
