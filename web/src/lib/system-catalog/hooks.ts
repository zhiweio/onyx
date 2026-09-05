"use client";

import useSWR from "swr";
import { errorHandlingFetcher } from "@/lib/fetcher";
import {
  adminCatalogListKey,
  galleryDetailKey,
  galleryListKey,
} from "@/lib/system-catalog/api";
import type {
  AnyCatalogItem,
  CatalogItem,
  CatalogListResponse,
  GalleryKind,
  SystemReportTemplateItem,
  SystemScenarioItem,
  SystemSkillItem,
} from "@/lib/system-catalog/types";

function useCatalogList<T extends CatalogItem>(key: string | null) {
  const { data, error, isLoading, mutate } = useSWR<CatalogListResponse<T>>(
    key,
    errorHandlingFetcher,
  );
  return {
    data: data?.items ?? [],
    error,
    isLoading,
    refresh: mutate,
  };
}

export function useGallerySkills(enabled = true) {
  return useCatalogList<SystemSkillItem>(
    enabled ? galleryListKey("skills") : null,
  );
}

export function useGalleryScenarios(enabled = true) {
  return useCatalogList<SystemScenarioItem>(
    enabled ? galleryListKey("scenarios") : null,
  );
}

export function useGalleryReportTemplates(enabled = true) {
  return useCatalogList<SystemReportTemplateItem>(
    enabled ? galleryListKey("report-templates") : null,
  );
}

/** Detail fetch, used by the preview modal to pull the full body. */
export function useGalleryItem<T extends AnyCatalogItem>(
  kind: GalleryKind,
  entryId: string | undefined,
) {
  const { data, error, isLoading } = useSWR<T>(
    entryId ? galleryDetailKey(kind, entryId) : null,
    errorHandlingFetcher,
  );
  return { data, error, isLoading };
}

export function useCatalogEntries<T extends CatalogItem>(kind: GalleryKind) {
  return useCatalogList<T>(adminCatalogListKey(kind));
}
