/** Mirrors `backend/onyx/db/system_catalog/constants.py`. */
export const CATALOG_SLUG_MAX = 64;
export const CATALOG_NAME_MAX = 128;
export const CATALOG_SKILL_NAME_MAX = 64;
export const CATALOG_DESCRIPTION_MAX = 4_000;
export const CATALOG_BODY_MAX = 100_000;
export const CATALOG_TAG_MAX = 32;
export const CATALOG_TAGS_MAX_COUNT = 20;

export function normalizeCatalogTag(raw: string): string {
  return raw.trim().toLowerCase();
}

export function canAcceptCatalogTag(
  tag: string,
  existing: readonly string[]
): boolean {
  return (
    tag.length > 0 &&
    tag.length <= CATALOG_TAG_MAX &&
    existing.length < CATALOG_TAGS_MAX_COUNT &&
    !existing.includes(tag)
  );
}
