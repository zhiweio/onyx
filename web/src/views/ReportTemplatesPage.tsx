"use client";

import { useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import type { Route } from "next";
import { useTranslations } from "next-intl";
import { Button, InputTypeIn, MessageCard, Tabs } from "@opal/components";
import {
  ConfirmationModalLayout,
  IllustrationContent,
  SettingsLayouts,
  toast,
} from "@opal/layouts";
import SvgNoResult from "@opal/illustrations/no-result";
import { SvgFileText, SvgPlus, SvgSimpleLoader, SvgTrash } from "@opal/icons";
import TextSeparator from "@/refresh-components/TextSeparator";
import useOnMount from "@/hooks/useOnMount";
import { useReportTemplates } from "@/lib/report-templates/hooks";
import {
  deleteReportTemplate,
  ReportTemplateRequestError,
} from "@/lib/report-templates/api";
import type { ReportTemplate } from "@/lib/report-templates/types";
import ReportTemplateCard from "@/sections/cards/ReportTemplateCard";
import { CRAFT_REPORT_TEMPLATES_PATH } from "@/app/craft/v1/constants";
import GalleryGrid from "@/sections/gallery/GalleryGrid";
import GalleryPreviewModal from "@/sections/modals/gallery/GalleryPreviewModal";
import { useGalleryReportTemplates } from "@/lib/system-catalog/hooks";
import { useGalleryTab } from "@/lib/system-catalog/useGalleryTab";

export default function ReportTemplatesPage() {
  const t = useTranslations("craft.reportTemplates");
  const tGallery = useTranslations("craft.gallery");
  const router = useRouter();
  const { data: templates, error, isLoading, refresh } = useReportTemplates();
  const [searchQuery, setSearchQuery] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<ReportTemplate | null>(null);
  const [deleting, setDeleting] = useState(false);
  const searchInputRef = useRef<HTMLInputElement>(null);

  const gallery = useGalleryTab({
    kind: "report-templates",
    onForked: async () => {
      await refresh();
    },
  });
  const {
    data: galleryItems,
    error: galleryError,
    isLoading: galleryLoading,
  } = useGalleryReportTemplates(gallery.tab === "gallery");

  useOnMount(() => {
    searchInputRef.current?.focus();
  });

  const visibleTemplates = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) return templates;
    return templates.filter(
      (template) =>
        template.name.toLowerCase().includes(query) ||
        template.slug.toLowerCase().includes(query) ||
        template.description.toLowerCase().includes(query),
    );
  }, [templates, searchQuery]);

  function openEditor(template: ReportTemplate) {
    // SAFETY: template.id is a UUID path segment under /craft/v1/report-templates.
    router.push(`${CRAFT_REPORT_TEMPLATES_PATH}/edit/${template.id}` as Route);
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await deleteReportTemplate(deleteTarget.id);
      setDeleteTarget(null);
      await refresh();
      toast.success(t("toasts.deleted.message"));
    } catch (deleteError) {
      console.error(deleteError);
      if (
        deleteError instanceof ReportTemplateRequestError &&
        deleteError.status === 409
      ) {
        toast.error(t("toasts.deleteBlocked.message"));
      } else {
        toast.error(
          deleteError instanceof Error
            ? deleteError.message
            : t("toasts.deleteFailed.message"),
        );
      }
    } finally {
      setDeleting(false);
    }
  }

  return (
    <SettingsLayouts.Root data-testid="ReportTemplatesPage/container">
      <SettingsLayouts.Header
        icon={SvgFileText}
        title={t("page.title.text")}
        description={t("page.description.text")}
        rightChildren={
          gallery.tab === "mine" ? (
            <Button
              icon={SvgPlus}
              onClick={() =>
                // SAFETY: /new is a static child of the report-templates list route.
                router.push(`${CRAFT_REPORT_TEMPLATES_PATH}/new` as Route)
              }
            >
              {t("page.createButton.label")}
            </Button>
          ) : undefined
        }
      >
        <div className="flex flex-col gap-2">
          <Tabs
            value={gallery.tab}
            onValueChange={(value) =>
              gallery.setTab(value as "gallery" | "mine")
            }
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
          <InputTypeIn
            ref={searchInputRef}
            placeholder={t("page.search.placeholder")}
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            searchIcon
          />
        </div>
      </SettingsLayouts.Header>

      <SettingsLayouts.Body>
        {gallery.tab === "gallery" ? (
          <GalleryGrid
            items={galleryItems}
            icon={SvgFileText}
            isLoading={galleryLoading}
            error={galleryError}
            searchQuery={searchQuery}
            category={gallery.category}
            onCategoryChange={gallery.setCategory}
            onPreview={gallery.setPreviewItem}
            onFork={gallery.forkItem}
            forkingId={gallery.forkingId}
          />
        ) : (
          <>
            {isLoading && <SvgSimpleLoader />}

            {error && !isLoading && (
              <MessageCard
                variant="error"
                title={t("error.title")}
                description={t("error.description")}
              />
            )}

            {!isLoading && !error && (
              <>
                {visibleTemplates.length === 0 ? (
                  <IllustrationContent
                    illustration={SvgNoResult}
                    title={
                      templates.length === 0
                        ? t("empty.none.title")
                        : t("empty.search.title")
                    }
                    description={
                      templates.length === 0
                        ? t("empty.none.description")
                        : t("empty.search.description")
                    }
                  />
                ) : (
                  <>
                    <section className="flex flex-col gap-2">
                      <div className="w-full grid grid-cols-1 md:grid-cols-2 gap-2">
                        {visibleTemplates.map((template) => (
                          <ReportTemplateCard
                            key={template.id}
                            template={template}
                            onClick={openEditor}
                            onEdit={openEditor}
                            onDelete={setDeleteTarget}
                          />
                        ))}
                      </div>
                    </section>
                    <TextSeparator
                      text={t("page.count.label", {
                        count: visibleTemplates.length,
                      })}
                    />
                  </>
                )}
              </>
            )}
          </>
        )}
      </SettingsLayouts.Body>

      {gallery.previewItem && (
        <GalleryPreviewModal
          kind="report-templates"
          entryId={gallery.previewItem.id}
          fallbackTitle={gallery.previewItem.name}
          onClose={() => gallery.setPreviewItem(null)}
          onFork={(entryId) => void gallery.fork(entryId)}
          forking={gallery.forkingId !== null}
        />
      )}

      {deleteTarget && (
        <ConfirmationModalLayout
          icon={SvgTrash}
          title={t("delete.title", { name: deleteTarget.name })}
          description={
            deleteTarget.referenced_count > 0
              ? t("delete.blocked.description")
              : t("delete.description")
          }
          onClose={deleting ? undefined : () => setDeleteTarget(null)}
          submit={
            <Button
              variant="danger"
              disabled={deleting || deleteTarget.referenced_count > 0}
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
