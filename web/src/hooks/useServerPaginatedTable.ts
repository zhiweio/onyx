"use client";

import { useMemo, useState } from "react";
import useSWR, { type SWRConfiguration } from "swr";
import type { SortingState } from "@tanstack/react-table";
import { useDebouncedValue } from "./useDebouncedValue";

/** Envelope every server-paginated list endpoint returns. */
export interface PaginatedResult<T> {
  items: T[];
  total: number;
}

export interface ServerPaginatedLoaderArgs {
  offset: number;
  limit: number;
  q: string;
}

interface UseServerPaginatedTableOptions<T> {
  /** Serialization of the current filters; a change resets to the first page. */
  requestKey: string;
  /** Fetches a single page. Receives the debounced search term. */
  loader: (args: ServerPaginatedLoaderArgs) => Promise<PaginatedResult<T>>;
  pageSize: number;
  /** When false, no request is made. @default true */
  enabled?: boolean;
  swrOptions?: SWRConfiguration<PaginatedResult<T>>;
}

const SEARCH_DEBOUNCE_MS = 300;

/**
 * Shared controller for opal `Table` in `serverSide` mode: debounced search
 * input, page state with reset-on-filter-change, and race-safe fetching via
 * SWR keyed on the request + page.
 */
export function useServerPaginatedTable<T>({
  requestKey,
  loader,
  pageSize,
  enabled = true,
  swrOptions,
}: UseServerPaginatedTableOptions<T>) {
  const [searchInput, setSearchInput] = useState("");
  const searchTerm = useDebouncedValue(searchInput, SEARCH_DEBOUNCE_MS);

  const [pageIndex, setPageIndex] = useState(0);
  const effectiveKey = `${requestKey}\0${searchTerm}`;
  const [keySnapshot, setKeySnapshot] = useState(effectiveKey);
  const nextPageIndex = keySnapshot !== effectiveKey ? 0 : pageIndex;
  if (keySnapshot !== effectiveKey) {
    setKeySnapshot(effectiveKey);
    setPageIndex(0);
  }

  const { data, error, isLoading, isValidating, mutate } = useSWR(
    enabled ? ["server-paginated-table", effectiveKey, nextPageIndex] : null,
    () =>
      loader({
        offset: nextPageIndex * pageSize,
        limit: pageSize,
        q: searchTerm,
      }),
    { keepPreviousData: true, shouldRetryOnError: false, ...swrOptions }
  );

  const rows = useMemo(() => data?.items ?? [], [data]);
  const total = data?.total ?? 0;
  const tableLoading = isLoading || isValidating;

  const serverSide = useMemo(
    () => ({
      totalItems: total,
      isLoading: tableLoading,
      onSortingChange: (_sorting: SortingState) => undefined,
      onPaginationChange: (nextPage: number, _pageSize: number) =>
        setPageIndex(nextPage),
      onSearchTermChange: () => undefined,
    }),
    [total, tableLoading]
  );

  const searchInputProps = useMemo(
    () => ({
      value: searchInput,
      onChange: (event: React.ChangeEvent<HTMLInputElement>) =>
        setSearchInput(event.target.value),
    }),
    [searchInput]
  );

  return {
    rows,
    total,
    isLoading: tableLoading,
    error,
    data,
    searchTerm,
    searchInputProps,
    setSearchInput,
    setPageIndex,
    reload: mutate,
    serverSide,
  };
}
