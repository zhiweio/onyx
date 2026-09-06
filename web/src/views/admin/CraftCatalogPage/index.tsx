"use client";

import { useCallback, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { Button, InputTypeIn, MessageCard, Tabs, Tag } from "@opal/components";
import {
  ConfirmationModalLayout,
  IllustrationContent,
  InputVertical,
  SettingsLayouts,
  toast,
} from "@opal/layouts";
import { InputTextArea } from "@opal/components";
import SvgNoResult from "@opal/illustrations/no-result";
import { SvgSimpleLoader, SvgTrash, SvgUploadCloud } from "@opal/icons";
import { Content } from "@opal/layouts";
import { Card } from "@/refresh-components/cards";
import { ADMIN_ROUTES } from "@/lib/admin-routes";
import { useCatalogEntries } from "@/lib/system-catalog/hooks";
import {
  catalogReportTemplateDocxUrl,
  deleteCatalogEntry,
  publishCatalogEntry,
  SystemCatalogRequestError,
  unpublishCatalogEntry,
  uploadCatalogReportTemplateDocx,
} from "@/lib/system-catalog/api";
import {
  categoryMessageKey,
  categoryTagColor,
  filterCatalogItems,
  isDocxCatalogTemplate,
  publishStatusMessageKey,
  publishStatusTagColor,
  type CatalogItem,
  type GalleryKind,
  type SystemReportTemplateItem,
} from "@/lib/system-catalog/types";
import DocxTemplateSection from "@/sections/reportTemplates/DocxTemplateSection";

const KIND_TABS: readonly GalleryKind[] = [
  "skills",
  "scenarios",
  "report-templates",
] as const;

// Literal keys under `admin.craftCatalog`, not copy — the union keeps `t()`
// statically checked.
type KindLabelKey =
  | "tabs.skills.label"
  | "tabs.scenarios.label"
  | "tabs.reportTemplates.label";

function kindLabelKey(kind: GalleryKind): KindLabelKey {
  switch (kind) {
    case "skills":
      return "tabs.skills.label";
    case "scenarios":
      return "tabs.scenarios.label";
    case "report-templates":
      return "tabs.reportTemplates.label";
  }
}

export default function CraftCatalogPage() {
  const t = useTranslations("admin.craftCatalog");
  const tGallery = useTranslations("craft.gallery");
  const [kind, setKind] = useState<GalleryKind>("skills");
  const [searchQuery, setSearchQuery] = useState("");
  const [publishTarget, setPublishTarget] = useState<CatalogItem | null>(null);
  const [changelog, setChangelog] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<CatalogItem | null>(null);
  const [pending, setPending] = useState(false);

  const { data: entries, error, isLoading, refresh } = useCatalogEntries(kind);

  const visibleEntries = useMemo(
    () => filterCatalogItems(entries, { query: searchQuery }),
    [entries, searchQuery],
  );

  const runAction = useCallback(
    async (action: () => Promise<void>, successMessage: string) => {
      setPending(true);
      try {
        await action();
        await refresh();
        toast.success(successMessage);
        return true;
      } catch (actionError) {
        console.error(actionError);
        toast.error(
          actionError instanceof SystemCatalogRequestError ||
            actionError instanceof Error
            ? actionError.message
            : t("toasts.actionFailed.message"),
        );
        return false;
      } finally {
        setPending(false);
      }
    },
    [refresh, t],
  );

  async function handlePublish() {
    if (!publishTarget) return;
    const ok = await runAction(
      async () => {
        await publishCatalogEntry(kind, publishTarget.id, changelog);
      },
      t("toasts.published.message", { name: publishTarget.name }),
    );
    if (ok) {
      setPublishTarget(null);
      setChangelog("");
    }
  }

  async function handleUnpublish(entry: CatalogItem) {
    await runAction(
      async () => {
        await unpublishCatalogEntry(kind, entry.id);
      },
      t("toasts.unpublished.message", { name: entry.name }),
    );
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    const ok = await runAction(
      () => deleteCatalogEntry(kind, deleteTarget.id),
      t("toasts.deleted.message", { name: deleteTarget.name }),
    );
    if (ok) setDeleteTarget(null);
  }

  return (
    <SettingsLayouts.Root data-testid="CraftCatalogPage/container">
      <SettingsLayouts.Header
        icon={ADMIN_ROUTES.CRAFT_CATALOG.icon}
        title={t("header.title")}
        description={t("header.description")}
      >
        <div className="flex flex-col gap-2">
          <Tabs
            value={kind}
            onValueChange={(value) => setKind(value as GalleryKind)}
          >
            <Tabs.List>
              {KIND_TABS.map((value) => (
                <Tabs.Trigger key={value} value={value}>
                  {t(kindLabelKey(value))}
                </Tabs.Trigger>
              ))}
            </Tabs.List>
          </Tabs>
          <InputTypeIn
            placeholder={t("search.placeholder")}
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            searchIcon
          />
        </div>
      </SettingsLayouts.Header>

      <SettingsLayouts.Body>
        {isLoading && <SvgSimpleLoader />}

        {error && !isLoading && (
          <MessageCard
            variant="error"
            title={t("error.title")}
            description={t("error.description")}
          />
        )}

        {!isLoading && !error && visibleEntries.length === 0 && (
          <IllustrationContent
            illustration={SvgNoResult}
            title={t("empty.title")}
            description={t("empty.description")}
          />
        )}

        {!isLoading && !error && visibleEntries.length > 0 && (
          <div className="flex flex-col gap-2">
            {visibleEntries.map((entry) => {
              const published = entry.publish_status === "PUBLISHED";
              return (
                <Card key={entry.id} variant="primary">
                  <div className="flex flex-row items-center justify-between gap-2 w-full">
                    <div className="flex min-w-0 flex-col gap-1">
                      <Content
                        title={entry.name}
                        sizePreset="main-ui"
                        variant="body"
                      />
                      <Content
                        title={entry.description || entry.slug}
                        sizePreset="secondary"
                        variant="body"
                        color="muted"
                      />
                      <div className="flex flex-row flex-wrap items-center gap-1">
                        <Tag
                          size="sm"
                          color={publishStatusTagColor(entry.publish_status)}
                          title={t(
                            publishStatusMessageKey(entry.publish_status),
                          )}
                        />
                        <Tag
                          size="sm"
                          color={categoryTagColor(entry.category)}
                          title={tGallery(categoryMessageKey(entry.category))}
                        />
                        <Content
                          title={tGallery("card.version.label", {
                            version: entry.version,
                          })}
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
                            <Tag
                              size="sm"
                              color="green"
                              title={t("word.badge.label")}
                            />
                          </span>
                        )}
                      </div>
                      {kind === "report-templates" && (
                        <DocxTemplateSection
                          template={entry as SystemReportTemplateItem}
                          disabled={pending}
                          onUploaded={() => {
                            void refresh();
                          }}
                          upload={uploadCatalogReportTemplateDocx}
                          downloadUrl={catalogReportTemplateDocxUrl}
                        />
                      )}
                    </div>
                    <div className="flex shrink-0 items-center gap-1">
                      {published ? (
                        <>
                          <Button
                            prominence="secondary"
                            size="sm"
                            disabled={pending}
                            onClick={() => setPublishTarget(entry)}
                          >
                            {t("actions.republish.label")}
                          </Button>
                          <Button
                            prominence="secondary"
                            size="sm"
                            disabled={pending}
                            onClick={() => void handleUnpublish(entry)}
                          >
                            {t("actions.unpublish.label")}
                          </Button>
                        </>
                      ) : (
                        <Button
                          size="sm"
                          disabled={pending}
                          onClick={() => setPublishTarget(entry)}
                        >
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
                        onClick={() => setDeleteTarget(entry)}
                      />
                    </div>
                  </div>
                </Card>
              );
            })}
          </div>
        )}
      </SettingsLayouts.Body>

      {publishTarget && (
        <ConfirmationModalLayout
          icon={SvgUploadCloud}
          title={t("publish.title", { name: publishTarget.name })}
          description={t("publish.description")}
          onClose={pending ? undefined : () => setPublishTarget(null)}
          submit={
            <Button disabled={pending} onClick={() => void handlePublish()}>
              {t("publish.confirm.label")}
            </Button>
          }
        >
          <InputVertical withLabel title={t("publish.changelog.label")}>
            <InputTextArea
              value={changelog}
              onChange={(event) => setChangelog(event.target.value)}
              placeholder={t("publish.changelog.placeholder")}
            />
          </InputVertical>
        </ConfirmationModalLayout>
      )}

      {deleteTarget && (
        <ConfirmationModalLayout
          icon={SvgTrash}
          title={t("delete.title", { name: deleteTarget.name })}
          description={t("delete.description")}
          onClose={pending ? undefined : () => setDeleteTarget(null)}
          submit={
            <Button
              variant="danger"
              disabled={pending}
              onClick={() => void handleDelete()}
            >
              {t("delete.confirm.label")}
            </Button>
          }
        />
      )}
    </SettingsLayouts.Root>
  );
}
