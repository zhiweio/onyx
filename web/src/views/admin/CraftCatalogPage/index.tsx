"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import type { Route } from "next";
import { useTranslations } from "next-intl";
import { Button, InputTypeIn, MessageCard, Tabs } from "@opal/components";
import {
  ConfirmationModalLayout,
  Content,
  IllustrationContent,
  InputVertical,
  SettingsLayouts,
  toast,
} from "@opal/layouts";
import { InputTextArea } from "@opal/components";
import SvgNoResult from "@opal/illustrations/no-result";
import { SvgPlus, SvgSimpleLoader, SvgTrash, SvgUploadCloud } from "@opal/icons";
import { ADMIN_ROUTES } from "@/lib/admin-routes";
import { useCatalogEntries } from "@/lib/system-catalog/hooks";
import {
  deleteCatalogEntry,
  publishCatalogEntry,
  SystemCatalogRequestError,
  unpublishCatalogEntry,
  updateCatalogEntry,
  type CatalogPatchInput,
} from "@/lib/system-catalog/api";
import {
  categoryMessageKey,
  collectCatalogCategories,
  filterCatalogItems,
  groupCatalogItemsByCategory,
  publishStatusMessageKey,
  type CatalogItem,
  type CatalogViewMode,
  type GalleryKind,
  type SystemCatalogCategory,
  type SystemCatalogPublishStatus,
} from "@/lib/system-catalog/types";
import { clampPage, slicePage } from "@/lib/browse/page";
import BrowsePagination from "@/sections/gallery/BrowsePagination";
import {
  CatalogCategoryChips,
  CatalogViewToggle,
} from "@/sections/gallery/CatalogBrowseControls";
import CatalogAdminEntry from "@/views/admin/CraftCatalogPage/CatalogAdminEntry";
import EditCatalogModal from "@/views/admin/CraftCatalogPage/EditCatalogModal";

const KIND_TABS: readonly GalleryKind[] = [
  "skills",
  "scenarios",
  "report-templates",
] as const;

const STATUS_FILTERS: readonly (SystemCatalogPublishStatus | "all")[] = [
  "all",
  "PUBLISHED",
  "DRAFT",
  "ARCHIVED",
] as const;

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
  const router = useRouter();
  const [kind, setKind] = useState<GalleryKind>("skills");
  const [searchQuery, setSearchQuery] = useState("");
  const [category, setCategory] = useState<SystemCatalogCategory | "all">(
    "all",
  );
  const [status, setStatus] = useState<SystemCatalogPublishStatus | "all">(
    "all",
  );
  const [view, setView] = useState<CatalogViewMode>("cards");
  const [page, setPage] = useState(1);
  const [publishTarget, setPublishTarget] = useState<CatalogItem | null>(null);
  const [changelog, setChangelog] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<CatalogItem | null>(null);
  const [editTarget, setEditTarget] = useState<CatalogItem | null>(null);
  const [pending, setPending] = useState(false);

  const { data: entries, error, isLoading, refresh } = useCatalogEntries(kind);

  const categories = useMemo(
    () => collectCatalogCategories(entries),
    [entries],
  );
  const visibleEntries = useMemo(
    () =>
      filterCatalogItems(entries, {
        query: searchQuery,
        category,
        statuses:
          status === "all" ? ["DRAFT", "PUBLISHED"] : [status],
      }),
    [entries, searchQuery, category, status],
  );
  const orderedEntries = useMemo(() => {
    if (category !== "all") {
      return visibleEntries;
    }
    return groupCatalogItemsByCategory(visibleEntries).flatMap(
      (group) => group.items,
    );
  }, [category, visibleEntries]);

  useEffect(() => {
    setPage(1);
  }, [kind, searchQuery, category, status, view]);

  const safePage = clampPage(page, orderedEntries.length);
  const pageEntries = slicePage(orderedEntries, safePage);
  const groups = useMemo(() => {
    if (category !== "all") {
      return [{ category, items: pageEntries }];
    }
    return groupCatalogItemsByCategory(pageEntries);
  }, [category, pageEntries]);
  const showGroupHeaders = category === "all" && groups.length > 1;

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

  async function handleEditSave(input: CatalogPatchInput) {
    if (!editTarget) return;
    const ok = await runAction(
      async () => {
        await updateCatalogEntry(kind, editTarget.id, input);
      },
      t("toasts.updated.message", { name: input.name ?? editTarget.name }),
    );
    if (ok) setEditTarget(null);
  }

  function handleEdit(entry: CatalogItem) {
    if (kind === "scenarios") {
      router.push(`/admin/craft/catalog/scenarios/edit/${entry.id}` as Route);
      return;
    }
    setEditTarget(entry);
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
            onValueChange={(value) => {
              setKind(value as GalleryKind);
              setCategory("all");
              setStatus("all");
            }}
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

        {!isLoading && !error && (
          <div className="flex flex-col gap-3">
            <div className="flex flex-row flex-wrap items-center justify-between gap-2">
              <div className="flex flex-col gap-2">
                <CatalogCategoryChips
                  categories={categories}
                  category={category}
                  onCategoryChange={setCategory}
                  label={(key) => tGallery(key)}
                />
                <div
                  className="flex flex-row flex-wrap gap-1"
                  data-testid="CraftCatalog/status"
                >
                  {STATUS_FILTERS.map((value) => (
                    <Button
                      key={value}
                      prominence={status === value ? "primary" : "secondary"}
                      size="sm"
                      onClick={() => setStatus(value)}
                    >
                      {value === "all"
                        ? tGallery(categoryMessageKey("all"))
                        : t(publishStatusMessageKey(value))}
                    </Button>
                  ))}
                </div>
              </div>
              <div className="flex items-center gap-2">
                {kind === "scenarios" && (
                  <Button
                    size="sm"
                    icon={SvgPlus}
                    onClick={() =>
                      router.push(
                        "/admin/craft/catalog/scenarios/new" as Route
                      )
                    }
                  >
                    {t("actions.createScenario.label")}
                  </Button>
                )}
                {visibleEntries.length > 0 && (
                  <CatalogViewToggle
                    view={view}
                    onViewChange={setView}
                    cardsTooltip={t("view.cards.tooltip")}
                    listTooltip={t("view.list.tooltip")}
                  />
                )}
              </div>
            </div>

            {visibleEntries.length === 0 ? (
              <IllustrationContent
                illustration={SvgNoResult}
                title={
                  entries.length === 0
                    ? t("empty.title")
                    : t("empty.search.title")
                }
                description={
                  entries.length === 0
                    ? t("empty.description")
                    : t("empty.search.description")
                }
              />
            ) : (
              groups.map((group) => (
                <section
                  key={group.category}
                  className="flex flex-col gap-2"
                  data-testid={`CraftCatalog/group-${group.category}`}
                >
                  {showGroupHeaders && (
                    <Content
                      title={tGallery(categoryMessageKey(group.category))}
                      sizePreset="section"
                      variant="heading"
                    />
                  )}
                  <div
                    className={
                      view === "cards"
                        ? "grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2"
                        : "flex flex-col gap-1"
                    }
                  >
                    {group.items.map((entry) => (
                      <CatalogAdminEntry
                        key={entry.id}
                        entry={entry}
                        view={view}
                        pending={pending}
                        showDocx={kind === "report-templates"}
                        onEdit={handleEdit}
                        onPublish={setPublishTarget}
                        onUnpublish={(item) => void handleUnpublish(item)}
                        onDelete={setDeleteTarget}
                        onDocxUploaded={() => {
                          void refresh();
                        }}
                      />
                    ))}
                  </div>
                </section>
              ))
            )}
            {visibleEntries.length > 0 && (
              <BrowsePagination
                page={safePage}
                totalItems={visibleEntries.length}
                onPageChange={setPage}
                units={tGallery("pagination.units")}
              />
            )}
          </div>
        )}
      </SettingsLayouts.Body>

      {editTarget && (
        <EditCatalogModal
          kind={kind}
          item={editTarget}
          pending={pending}
          onClose={() => setEditTarget(null)}
          onSave={handleEditSave}
        />
      )}

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
