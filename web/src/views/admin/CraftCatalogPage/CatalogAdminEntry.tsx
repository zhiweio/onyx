"use client";

import { useTranslations } from "next-intl";
import { Button, Tag } from "@opal/components";
import { Content } from "@opal/layouts";
import { SvgEdit, SvgTrash } from "@opal/icons";
import { Card } from "@/refresh-components/cards";
import {
  catalogReportTemplateDocxUrl,
  uploadCatalogReportTemplateDocx,
} from "@/lib/system-catalog/api";
import {
  categoryMessageKey,
  categoryTagColor,
  isDocxCatalogTemplate,
  isReportTemplateItem,
  publishStatusMessageKey,
  publishStatusTagColor,
  type CatalogItem,
  type CatalogViewMode,
} from "@/lib/system-catalog/types";
import DocxTemplateSection from "@/sections/reportTemplates/DocxTemplateSection";

interface CatalogAdminEntryProps {
  entry: CatalogItem;
  view: CatalogViewMode;
  pending: boolean;
  showDocx: boolean;
  onEdit: (entry: CatalogItem) => void;
  onPublish: (entry: CatalogItem) => void;
  onUnpublish: (entry: CatalogItem) => void;
  onDelete: (entry: CatalogItem) => void;
  onDocxUploaded: () => void;
}

export default function CatalogAdminEntry({
  entry,
  view,
  pending,
  showDocx,
  onEdit,
  onPublish,
  onUnpublish,
  onDelete,
  onDocxUploaded,
}: CatalogAdminEntryProps) {
  const t = useTranslations("admin.craftCatalog");
  const tGallery = useTranslations("craft.gallery");
  const published = entry.publish_status === "PUBLISHED";

  const meta = (
    <div className="flex flex-row flex-wrap items-center gap-1">
      <Tag
        size="sm"
        color={publishStatusTagColor(entry.publish_status)}
        title={t(publishStatusMessageKey(entry.publish_status))}
      />
      <Tag
        size="sm"
        color={categoryTagColor(entry.category)}
        title={tGallery(categoryMessageKey(entry.category))}
      />
      <Content
        title={tGallery("card.version.label", { version: entry.version })}
        sizePreset="secondary"
        variant="body"
        color="muted"
      />
      <Content
        title={entry.slug}
        sizePreset="secondary"
        variant="body"
        color="muted"
      />
      {isDocxCatalogTemplate(entry) && (
        <span data-testid="CraftCatalog/word">
          <Tag size="sm" color="green" title={t("word.badge.label")} />
        </span>
      )}
    </div>
  );

  const actions = (
    <div className="flex shrink-0 items-center gap-1">
      <Button
        prominence="tertiary"
        size="sm"
        icon={SvgEdit}
        disabled={pending}
        tooltip={t("actions.edit.tooltip")}
        aria-label={t("actions.edit.tooltip")}
        data-testid="CraftCatalog/edit"
        onClick={() => onEdit(entry)}
      />
      {published ? (
        <>
          <Button
            prominence="secondary"
            size="sm"
            disabled={pending}
            onClick={() => onPublish(entry)}
          >
            {t("actions.republish.label")}
          </Button>
          <Button
            prominence="secondary"
            size="sm"
            disabled={pending}
            onClick={() => onUnpublish(entry)}
          >
            {t("actions.unpublish.label")}
          </Button>
        </>
      ) : (
        <Button size="sm" disabled={pending} onClick={() => onPublish(entry)}>
          {t("actions.publish.label")}
        </Button>
      )}
      <Button
        prominence="tertiary"
        size="sm"
        icon={SvgTrash}
        disabled={pending || published}
        tooltip={
          published
            ? t("actions.deleteBlocked.tooltip")
            : t("actions.delete.tooltip")
        }
        aria-label={t("actions.delete.tooltip")}
        onClick={() => onDelete(entry)}
      />
    </div>
  );

  const docx =
    showDocx && isReportTemplateItem(entry) ? (
      <div className="border-t border-border-01 pt-3">
        <DocxTemplateSection
          template={entry}
          disabled={pending}
          compact
          onUploaded={onDocxUploaded}
          upload={uploadCatalogReportTemplateDocx}
          downloadUrl={catalogReportTemplateDocxUrl}
        />
      </div>
    ) : null;

  if (view === "list") {
    return (
      <Card variant="primary">
        <div className="flex w-full flex-col gap-3">
          <div className="flex flex-row items-start justify-between gap-3">
            <div className="flex min-w-0 flex-1 flex-col gap-1.5">
              <Content
                title={entry.name}
                description={entry.description || entry.slug}
                sizePreset="main-ui"
                variant="section"
              />
              {meta}
            </div>
            {actions}
          </div>
          {docx}
        </div>
      </Card>
    );
  }

  return (
    <Card variant="primary" height="full">
      <div className="flex h-full w-full flex-col justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1.5">
          <Content title={entry.name} sizePreset="main-ui" variant="body" />
          <Content
            title={entry.description || entry.slug}
            sizePreset="secondary"
            variant="body"
            color="muted"
          />
          {meta}
          {docx}
        </div>
        {actions}
      </div>
    </Card>
  );
}
