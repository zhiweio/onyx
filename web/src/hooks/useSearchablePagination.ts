"use client";

import { useEffect, useMemo, useState } from "react";
import { clampPage, slicePage } from "@/lib/browse/page";

export interface SearchablePagination<T> {
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  /** Items matching the current query (all pages). */
  filtered: T[];
  /** Current page after clamping to the available page count. */
  safePage: number;
  /** Items on the current page. */
  pageItems: T[];
  setPage: (page: number) => void;
}

/**
 * Client-side search + pagination shared by every MCP list surface
 * (admin/mcp-actions, craft apps, chat preferences, agent editor).
 * Backends return full arrays, so paging happens entirely client-side.
 *
 * `matches` receives the lowercased trimmed query and must be stable
 * across renders (module-level or useCallback) to avoid re-filter loops.
 */
export function useSearchablePagination<T>(
  items: T[],
  matches: (item: T, query: string) => boolean
): SearchablePagination<T> {
  const [searchQuery, setSearchQuery] = useState("");
  const [page, setPage] = useState(1);

  const filtered = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) return items;
    return items.filter((item) => matches(item, query));
  }, [items, searchQuery, matches]);

  useEffect(() => {
    setPage(1);
  }, [searchQuery]);

  const safePage = clampPage(page, filtered.length);
  const pageItems = slicePage(filtered, safePage);

  return {
    searchQuery,
    setSearchQuery,
    filtered,
    safePage,
    pageItems,
    setPage,
  };
}

/** Shared matcher for anything shaped like an MCP server listing. */
export function mcpServerMatches(
  server: { name: string; description?: string | null; server_url: string },
  query: string
): boolean {
  return (
    server.name.toLowerCase().includes(query) ||
    (server.description?.toLowerCase().includes(query) ?? false) ||
    server.server_url.toLowerCase().includes(query)
  );
}
