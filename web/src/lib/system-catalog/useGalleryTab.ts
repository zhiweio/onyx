"use client";

import { useCallback, useState } from "react";
import { useTranslations } from "next-intl";
import { toast } from "@opal/layouts";
import { forkGalleryItem } from "@/lib/system-catalog/api";
import type {
  CatalogItem,
  GalleryKind,
  SystemCatalogCategory,
} from "@/lib/system-catalog/types";

export type GalleryTab = "gallery" | "mine";

interface UseGalleryTabOptions {
  kind: GalleryKind;
  /** Refresh the user's own list so a fork shows up there immediately. */
  onForked: () => Promise<void>;
}

/**
 * Shared state for the "gallery / mine" tabs: which tab is active, the
 * category filter, the preview target, and the fork call.
 */
export function useGalleryTab({ kind, onForked }: UseGalleryTabOptions) {
  const t = useTranslations("craft.gallery");
  const [tab, setTab] = useState<GalleryTab>("mine");
  const [category, setCategory] = useState<SystemCatalogCategory | "all">(
    "all",
  );
  const [previewItem, setPreviewItem] = useState<CatalogItem | null>(null);
  const [forkingId, setForkingId] = useState<string | null>(null);

  const fork = useCallback(
    async (entryId: string) => {
      setForkingId(entryId);
      try {
        const result = await forkGalleryItem(kind, entryId);
        await onForked();
        setPreviewItem(null);
        setTab("mine");
        toast.success(t("toasts.forked.message", { name: result.name }));
      } catch (forkError) {
        console.error(forkError);
        toast.error(
          forkError instanceof Error
            ? forkError.message
            : t("toasts.forkFailed.message"),
        );
      } finally {
        setForkingId(null);
      }
    },
    [kind, onForked, t],
  );

  const forkItem = useCallback(
    (item: CatalogItem) => void fork(item.id),
    [fork],
  );

  return {
    tab,
    setTab,
    category,
    setCategory,
    previewItem,
    setPreviewItem,
    forkingId,
    fork,
    forkItem,
  };
}
