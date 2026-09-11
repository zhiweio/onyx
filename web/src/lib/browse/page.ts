/** Shared page size for gallery, library, and MCP browse lists. */
export const BROWSE_PAGE_SIZE = 12;

export function pageCount(
  totalItems: number,
  pageSize: number = BROWSE_PAGE_SIZE,
): number {
  if (totalItems <= 0) {
    return 1;
  }
  return Math.ceil(totalItems / pageSize);
}

export function clampPage(
  page: number,
  totalItems: number,
  pageSize: number = BROWSE_PAGE_SIZE,
): number {
  const pages = pageCount(totalItems, pageSize);
  return Math.min(Math.max(1, page), pages);
}

export function slicePage<T>(
  items: T[],
  page: number,
  pageSize: number = BROWSE_PAGE_SIZE,
): T[] {
  const safePage = clampPage(page, items.length, pageSize);
  const start = (safePage - 1) * pageSize;
  return items.slice(start, start + pageSize);
}
