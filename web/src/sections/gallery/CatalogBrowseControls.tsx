"use client";

import { Button } from "@opal/components";
import { SvgBlocks, SvgListTree } from "@opal/icons";
import {
  categoryMessageKey,
  type CatalogViewMode,
  type SystemCatalogCategory,
} from "@/lib/system-catalog/types";

interface CatalogCategoryChipsProps {
  categories: SystemCatalogCategory[];
  category: SystemCatalogCategory | "all";
  onCategoryChange: (category: SystemCatalogCategory | "all") => void;
  label: (key: ReturnType<typeof categoryMessageKey>) => string;
}

export function CatalogCategoryChips({
  categories,
  category,
  onCategoryChange,
  label,
}: CatalogCategoryChipsProps) {
  if (categories.length === 0) {
    return null;
  }

  return (
    <div
      className="flex flex-row flex-wrap gap-1"
      data-testid="CatalogBrowse/categories"
    >
      <Button
        prominence={category === "all" ? "primary" : "secondary"}
        size="sm"
        onClick={() => onCategoryChange("all")}
      >
        {label(categoryMessageKey("all"))}
      </Button>
      {categories.map((value) => (
        <Button
          key={value}
          prominence={category === value ? "primary" : "secondary"}
          size="sm"
          onClick={() => onCategoryChange(value)}
        >
          {label(categoryMessageKey(value))}
        </Button>
      ))}
    </div>
  );
}

interface CatalogViewToggleProps {
  view: CatalogViewMode;
  onViewChange: (view: CatalogViewMode) => void;
  cardsTooltip: string;
  listTooltip: string;
}

export function CatalogViewToggle({
  view,
  onViewChange,
  cardsTooltip,
  listTooltip,
}: CatalogViewToggleProps) {
  return (
    <div className="flex flex-row gap-1" data-testid="CatalogBrowse/view">
      <Button
        prominence={view === "cards" ? "primary" : "tertiary"}
        size="sm"
        icon={SvgBlocks}
        tooltip={cardsTooltip}
        aria-label={cardsTooltip}
        aria-pressed={view === "cards"}
        data-testid="CatalogBrowse/view-cards"
        onClick={() => onViewChange("cards")}
      />
      <Button
        prominence={view === "list" ? "primary" : "tertiary"}
        size="sm"
        icon={SvgListTree}
        tooltip={listTooltip}
        aria-label={listTooltip}
        aria-pressed={view === "list"}
        data-testid="CatalogBrowse/view-list"
        onClick={() => onViewChange("list")}
      />
    </div>
  );
}
