"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useTranslations } from "next-intl";
import { CatalogViewToggle } from "@/sections/gallery/CatalogBrowseControls";
import BrowsePagination from "@/sections/gallery/BrowsePagination";
import { clampPage, slicePage } from "@/lib/browse/page";
import type { CatalogViewMode } from "@/lib/system-catalog/types";

interface BrowseItemGridProps<T> {
  items: T[];
  resetKey: string;
  view: CatalogViewMode;
  onViewChange: (view: CatalogViewMode) => void;
  getKey: (item: T) => string;
  renderItem: (item: T, view: CatalogViewMode) => ReactNode;
  toolbarStart?: ReactNode;
}

export default function BrowseItemGrid<T>({
  items,
  resetKey,
  view,
  onViewChange,
  getKey,
  renderItem,
  toolbarStart,
}: BrowseItemGridProps<T>) {
  const t = useTranslations("craft.gallery");
  const [page, setPage] = useState(1);

  useEffect(() => {
    setPage(1);
  }, [resetKey]);

  const safePage = clampPage(page, items.length);
  const pageItems = slicePage(items, safePage);

  return (
    <div className="flex flex-col gap-2" data-testid="BrowseItemGrid/container">
      <div className="flex flex-row flex-wrap items-center justify-between gap-2">
        {toolbarStart ?? <span />}
        <CatalogViewToggle
          view={view}
          onViewChange={onViewChange}
          cardsTooltip={t("view.cards.tooltip")}
          listTooltip={t("view.list.tooltip")}
        />
      </div>
      <div
        className={
          view === "cards"
            ? "w-full grid grid-cols-1 md:grid-cols-2 gap-2"
            : "flex flex-col gap-1"
        }
      >
        {pageItems.map((item) => (
          <div key={getKey(item)}>{renderItem(item, view)}</div>
        ))}
      </div>
      <BrowsePagination
        page={safePage}
        totalItems={items.length}
        onPageChange={setPage}
        units={t("pagination.units")}
      />
    </div>
  );
}
