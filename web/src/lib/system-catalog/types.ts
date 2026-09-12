import type { ReportTemplateKind } from "@/lib/report-templates/types";

export type { ReportTemplateKind } from "@/lib/report-templates/types";

export type SystemCatalogCategory =
  | "TAX"
  | "BIOMED"
  | "OFFICE"
  | "DOCUMENT"
  | "CONTENT"
  | "ACADEMIC"
  | "REPORT"
  | "GRAPHIC"
  | "DEV_TOOL"
  | "GENERAL";

export type SystemCatalogPublishStatus = "DRAFT" | "PUBLISHED" | "ARCHIVED";

export type SystemCatalogOrigin = "BUILTIN" | "ADMIN";

export type GalleryKind = "skills" | "scenarios" | "report-templates";

export type CatalogViewMode = "cards" | "list";

export const SYSTEM_CATALOG_CATEGORIES: readonly SystemCatalogCategory[] = [
  "DOCUMENT",
  "OFFICE",
  "CONTENT",
  "ACADEMIC",
  "REPORT",
  "GRAPHIC",
  "DEV_TOOL",
  "TAX",
  "BIOMED",
  "GENERAL",
] as const;

/** Fields shared by every catalog entry, in both the gallery and admin views. */
export interface CatalogItem {
  id: string;
  slug: string;
  name: string;
  description: string;
  category: SystemCatalogCategory;
  tags: string[];
  publish_status: SystemCatalogPublishStatus;
  version: number;
  changelog: string;
  origin: SystemCatalogOrigin;
  published_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface SystemSkillItem extends CatalogItem {
  is_built_in_content: boolean;
  /** Only returned by the detail endpoint; listing skips bundle reads. */
  instructions_markdown: string | null;
}

export interface CatalogBoundSkill {
  slug: string;
  name: string;
  description: string;
  publish_status: SystemCatalogPublishStatus;
}

export interface CatalogBoundTemplate {
  slug: string;
  name: string;
}

export interface SystemScenarioItem extends CatalogItem {
  rules: Record<string, unknown>;
  skill_slugs: string[];
  report_template_slug: string | null;
  bound_skills?: CatalogBoundSkill[] | null;
  report_template?: CatalogBoundTemplate | null;
}

export interface SystemReportTemplateItem extends CatalogItem {
  body: string;
  kind: ReportTemplateKind;
  asset_filename: string | null;
}

export function isReportTemplateItem(
  item: CatalogItem
): item is SystemReportTemplateItem {
  return "kind" in item && "body" in item;
}

export function isSystemSkillItem(item: CatalogItem): item is SystemSkillItem {
  return "is_built_in_content" in item;
}

export function isDocxCatalogTemplate(
  item: CatalogItem
): item is SystemReportTemplateItem {
  return isReportTemplateItem(item) && item.kind === "DOCX";
}

export type AnyCatalogItem =
  | SystemSkillItem
  | SystemScenarioItem
  | SystemReportTemplateItem;

export interface CatalogListResponse<T extends CatalogItem> {
  items: T[];
}

export interface ForkResponse {
  id: string;
  name: string;
}

export interface CatalogFilters {
  query?: string;
  category?: SystemCatalogCategory | "all";
  statuses?: SystemCatalogPublishStatus[];
}

/**
 * Literal keys under `craft.gallery`, not copy. The unions keep `t()`
 * statically checked while these stay plain helpers.
 */
export type CatalogCategoryMessageKey =
  | "category.all.label"
  | "category.tax.label"
  | "category.biomed.label"
  | "category.office.label"
  | "category.document.label"
  | "category.content.label"
  | "category.academic.label"
  | "category.report.label"
  | "category.graphic.label"
  | "category.devTool.label"
  | "category.general.label";

export function categoryMessageKey(
  category: SystemCatalogCategory | "all"
): CatalogCategoryMessageKey {
  switch (category) {
    case "all":
      return "category.all.label";
    case "TAX":
      return "category.tax.label";
    case "BIOMED":
      return "category.biomed.label";
    case "OFFICE":
      return "category.office.label";
    case "DOCUMENT":
      return "category.document.label";
    case "CONTENT":
      return "category.content.label";
    case "ACADEMIC":
      return "category.academic.label";
    case "REPORT":
      return "category.report.label";
    case "GRAPHIC":
      return "category.graphic.label";
    case "DEV_TOOL":
      return "category.devTool.label";
    case "GENERAL":
      return "category.general.label";
  }
}

export type CatalogStatusMessageKey =
  | "status.draft.label"
  | "status.published.label"
  | "status.archived.label";

export function publishStatusMessageKey(
  status: SystemCatalogPublishStatus
): CatalogStatusMessageKey {
  switch (status) {
    case "DRAFT":
      return "status.draft.label";
    case "PUBLISHED":
      return "status.published.label";
    case "ARCHIVED":
      return "status.archived.label";
  }
}

/** Subset of the design system's TagColor that this feature uses. */
export type CatalogTagColor = "blue" | "purple" | "green" | "amber" | "gray";

export function categoryTagColor(
  category: SystemCatalogCategory
): CatalogTagColor {
  switch (category) {
    case "TAX":
      return "blue";
    case "BIOMED":
      return "purple";
    case "DOCUMENT":
      return "green";
    case "OFFICE":
      return "amber";
    case "CONTENT":
      return "amber";
    case "ACADEMIC":
      return "purple";
    case "REPORT":
      return "green";
    case "GRAPHIC":
      return "blue";
    case "DEV_TOOL":
      return "gray";
    case "GENERAL":
      return "gray";
  }
}

export function publishStatusTagColor(
  status: SystemCatalogPublishStatus
): CatalogTagColor {
  switch (status) {
    case "PUBLISHED":
      return "green";
    case "DRAFT":
      return "amber";
    case "ARCHIVED":
      return "gray";
  }
}

/**
 * A user's copy trails the gallery when the entry has been published again
 * since the fork was taken.
 */
export function isForkOutdated(
  forkVersion: number | null | undefined,
  upstreamVersion: number | null | undefined
): boolean {
  if (
    forkVersion === null ||
    forkVersion === undefined ||
    upstreamVersion === null ||
    upstreamVersion === undefined
  ) {
    return false;
  }
  return forkVersion < upstreamVersion;
}

export function filterCatalogItems<T extends CatalogItem>(
  items: T[],
  filters: CatalogFilters
): T[] {
  const query = filters.query?.trim().toLowerCase() ?? "";
  return items.filter((item) => {
    if (
      filters.category &&
      filters.category !== "all" &&
      item.category !== filters.category
    ) {
      return false;
    }
    if (filters.statuses && !filters.statuses.includes(item.publish_status)) {
      return false;
    }
    if (!query) return true;
    return (
      item.name.toLowerCase().includes(query) ||
      item.slug.toLowerCase().includes(query) ||
      item.description.toLowerCase().includes(query) ||
      item.tags.some((tag) => tag.toLowerCase().includes(query))
    );
  });
}

/** Categories actually present, so the filter bar never offers an empty one. */
export function collectCatalogCategories(
  items: CatalogItem[]
): SystemCatalogCategory[] {
  const present = new Set(items.map((item) => item.category));
  return SYSTEM_CATALOG_CATEGORIES.filter((category) => present.has(category));
}

/** Group items in the category display order used by the filter bar. */
export function groupCatalogItemsByCategory<T extends CatalogItem>(
  items: T[]
): { category: SystemCatalogCategory; items: T[] }[] {
  const grouped = new Map<SystemCatalogCategory, T[]>();
  for (const item of items) {
    const bucket = grouped.get(item.category);
    if (bucket) {
      bucket.push(item);
    } else {
      grouped.set(item.category, [item]);
    }
  }
  return SYSTEM_CATALOG_CATEGORIES.flatMap((category) => {
    const bucket = grouped.get(category);
    return bucket ? [{ category, items: bucket }] : [];
  });
}
