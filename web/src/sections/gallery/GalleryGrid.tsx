"use client";

import { useMemo } from "react";
import { useTranslations } from "next-intl";
import { Button, MessageCard } from "@opal/components";
import { IllustrationContent } from "@opal/layouts";
import SvgNoResult from "@opal/illustrations/no-result";
import { SvgSimpleLoader } from "@opal/icons";
import type { IconFunctionComponent } from "@opal/types";
import TextSeparator from "@/refresh-components/TextSeparator";
import GalleryCard from "@/sections/gallery/GalleryCard";
import {
  categoryMessageKey,
  collectCatalogCategories,
  filterCatalogItems,
  type CatalogItem,
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

  const categories = useMemo(() => collectCatalogCategories(items), [items]);
  const visibleItems = useMemo(
    () => filterCatalogItems(items, { query: searchQuery, category }),
    [items, searchQuery, category],
  );

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
      {categories.length > 1 && (
        <div className="flex flex-row flex-wrap gap-1">
          <Button
            prominence={category === "all" ? "primary" : "secondary"}
            size="sm"
            onClick={() => onCategoryChange("all")}
          >
            {t(categoryMessageKey("all"))}
          </Button>
          {categories.map((value) => (
            <Button
              key={value}
              prominence={category === value ? "primary" : "secondary"}
              size="sm"
              onClick={() => onCategoryChange(value)}
            >
              {t(categoryMessageKey(value))}
            </Button>
          ))}
        </div>
      )}

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
          <section className="flex flex-col gap-2">
            <div className="w-full grid grid-cols-1 md:grid-cols-2 gap-2">
              {visibleItems.map((item) => (
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
          </section>
          <TextSeparator
            text={t("count.label", { count: visibleItems.length })}
          />
        </>
      )}
    </div>
  );
}
