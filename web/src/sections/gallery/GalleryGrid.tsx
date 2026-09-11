"use client";

import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { MessageCard } from "@opal/components";
import { Content, IllustrationContent } from "@opal/layouts";
import SvgNoResult from "@opal/illustrations/no-result";
import { SvgSimpleLoader } from "@opal/icons";
import type { IconFunctionComponent } from "@opal/types";
import TextSeparator from "@/refresh-components/TextSeparator";
import BrowsePagination from "@/sections/gallery/BrowsePagination";
import {
  CatalogCategoryChips,
  CatalogViewToggle,
} from "@/sections/gallery/CatalogBrowseControls";
import GalleryCard from "@/sections/gallery/GalleryCard";
import { clampPage, slicePage } from "@/lib/browse/page";
import {
  categoryMessageKey,
  collectCatalogCategories,
  filterCatalogItems,
  groupCatalogItemsByCategory,
  type CatalogItem,
  type CatalogViewMode,
  type SystemCatalogCategory,
} from "@/lib/system-catalog/types";

export interface GalleryGridProps {
  items: CatalogItem[];
  icon: IconFunctionComponent;
  isLoading: boolean;
  error: unknown;
  searchQuery: string;
  category: SystemCatalogCategory | "all";
  onCategoryChange: (category: SystemCatalogCategory | "all") => void;
  onPreview?: (item: CatalogItem) => void;
  onFork?: (item: CatalogItem) => void;
  forkingId?: string | null;
}

export default function GalleryGrid({
  items,
  icon,
  isLoading,
  error,
  searchQuery,
  category,
  onCategoryChange,
  onPreview,
  onFork,
  forkingId,
}: GalleryGridProps) {
  const t = useTranslations("craft.gallery");
  const [view, setView] = useState<CatalogViewMode>("cards");
  const [page, setPage] = useState(1);

  const categories = useMemo(() => collectCatalogCategories(items), [items]);
  const visibleItems = useMemo(
    () => filterCatalogItems(items, { query: searchQuery, category }),
    [items, searchQuery, category],
  );
  const orderedItems = useMemo(() => {
    if (category !== "all") {
      return visibleItems;
    }
    return groupCatalogItemsByCategory(visibleItems).flatMap(
      (group) => group.items,
    );
  }, [category, visibleItems]);

  useEffect(() => {
    setPage(1);
  }, [searchQuery, category, view]);

  const safePage = clampPage(page, orderedItems.length);
  const pageItems = slicePage(orderedItems, safePage);
  const groups = useMemo(() => {
    if (category !== "all") {
      return [{ category, items: pageItems }];
    }
    return groupCatalogItemsByCategory(pageItems);
  }, [category, pageItems]);
  const showGroupHeaders = category === "all" && groups.length > 1;

  if (isLoading) {
    return <SvgSimpleLoader />;
  }

  if (error) {
    return (
      <MessageCard
        variant="error"
        title={t("error.title")}
        description={t("error.description")}
      />
    );
  }

  return (
    <div className="flex flex-col gap-2" data-testid="GalleryGrid/container">
      <div className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CatalogCategoryChips
          categories={categories}
          category={category}
          onCategoryChange={onCategoryChange}
          label={(key) => t(key)}
        />
        {visibleItems.length > 0 && (
          <CatalogViewToggle
            view={view}
            onViewChange={setView}
            cardsTooltip={t("view.cards.tooltip")}
            listTooltip={t("view.list.tooltip")}
          />
        )}
      </div>

      {visibleItems.length === 0 ? (
        <IllustrationContent
          illustration={SvgNoResult}
          title={
            items.length === 0 ? t("empty.none.title") : t("empty.search.title")
          }
          description={
            items.length === 0
              ? t("empty.none.description")
              : t("empty.search.description")
          }
        />
      ) : (
        <>
          {groups.map((group) => (
            <section
              key={group.category}
              className="flex flex-col gap-2"
              data-testid={`GalleryGrid/group-${group.category}`}
            >
              {showGroupHeaders && (
                <Content
                  title={t(categoryMessageKey(group.category))}
                  sizePreset="section"
                  variant="heading"
                />
              )}
              {view === "cards" ? (
                <div className="w-full grid grid-cols-1 md:grid-cols-2 gap-2">
                  {group.items.map((item) => (
                    <GalleryCard
                      key={item.id}
                      item={item}
                      icon={icon}
                      onPreview={onPreview}
                      onFork={onFork}
                      forking={forkingId === item.id}
                    />
                  ))}
                </div>
              ) : (
                <div className="flex flex-col gap-1">
                  {group.items.map((item) => (
                    <GalleryCard
                      key={item.id}
                      item={item}
                      icon={icon}
                      layout="row"
                      onPreview={onPreview}
                      onFork={onFork}
                      forking={forkingId === item.id}
                    />
                  ))}
                </div>
              )}
            </section>
          ))}
          <BrowsePagination
            page={safePage}
            totalItems={visibleItems.length}
            onPageChange={setPage}
            units={t("pagination.units")}
          />
          <TextSeparator
            text={t("count.label", { count: visibleItems.length })}
          />
        </>
      )}
    </div>
  );
}
