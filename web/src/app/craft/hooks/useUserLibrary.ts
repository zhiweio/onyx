"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import useSWR from "swr";
import { SWR_KEYS } from "@/lib/swr-keys";
import {
  fetchLibraryTree,
  uploadLibraryFiles,
  uploadLibraryZip,
  createLibraryDirectory,
  deleteLibraryFile,
} from "@/app/craft/services/apiServices";
import type { LibraryEntry } from "@/app/craft/types/user-library";

const USER_LIBRARY_ROOT = "user_library";

export interface UseUserLibraryOptions {
  /** When false, skip fetching and clear transient UI state. */
  enabled?: boolean;
  onChanges?: () => void;
}

/**
 * Map a library tree path (`user_library/reports`) to the upload/create API
 * path (`/reports`). Root stays `/`.
 */
export function libraryEntryToApiPath(path: string): string {
  const cleaned = path.replace(/^\/+/, "").replace(/\/+$/, "");
  if (cleaned === USER_LIBRARY_ROOT) {
    return "/";
  }
  if (cleaned.startsWith(`${USER_LIBRARY_ROOT}/`)) {
    return `/${cleaned.slice(USER_LIBRARY_ROOT.length + 1)}`;
  }
  return cleaned ? `/${cleaned}` : "/";
}

function buildTreeFromFlatList(flatList: LibraryEntry[]): LibraryEntry[] {
  const pathToEntry = new Map<string, LibraryEntry>();

  for (const entry of flatList) {
    pathToEntry.set(entry.path, { ...entry, children: [] });
  }

  const rootEntries: LibraryEntry[] = [];

  for (const entry of flatList) {
    const entryWithChildren = pathToEntry.get(entry.path)!;
    const pathParts = entry.path.split("/");
    pathParts.pop();
    const parentPath = pathParts.join("/");
    const parent = pathToEntry.get(parentPath);
    if (parent && parent.children) {
      parent.children.push(entryWithChildren);
    } else {
      rootEntries.push(entryWithChildren);
    }
  }

  return rootEntries;
}

function filterTree(entries: LibraryEntry[], query: string): LibraryEntry[] {
  const result: LibraryEntry[] = [];
  for (const entry of entries) {
    const children = entry.children ? filterTree(entry.children, query) : [];
    if (entry.name.toLowerCase().includes(query) || children.length > 0) {
      result.push({ ...entry, children });
    }
  }
  return result;
}

export function findLibraryEntry(
  entries: LibraryEntry[],
  path: string
): LibraryEntry | null {
  const normalized = path.replace(/\/$/, "");
  for (const entry of entries) {
    if (entry.path.replace(/\/$/, "") === normalized) {
      return entry;
    }
    if (entry.children?.length) {
      const found = findLibraryEntry(entry.children, normalized);
      if (found) return found;
    }
  }
  return null;
}

export function useUserLibrary({
  enabled = true,
  onChanges,
}: UseUserLibraryOptions = {}) {
  const t = useTranslations("craft.userLibrary");
  const [isUploading, setIsUploading] = useState(false);
  const [selectedEntry, setSelectedEntry] = useState<LibraryEntry | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [entryToDelete, setEntryToDelete] = useState<LibraryEntry | null>(null);
  const [isCreatingFolder, setIsCreatingFolder] = useState(false);
  const [isSubmittingFolder, setIsSubmittingFolder] = useState(false);
  const [newFolderName, setNewFolderName] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const uploadTargetPathRef = useRef<string>("/");
  const dragDepth = useRef(0);

  const {
    data: tree,
    error,
    isLoading,
    mutate,
  } = useSWR(enabled ? SWR_KEYS.buildUserLibraryTree : null, fetchLibraryTree, {
    revalidateOnFocus: false,
  });

  const hierarchicalTree = useMemo(() => {
    if (!tree) return [];
    return buildTreeFromFlatList(tree);
  }, [tree]);

  const trimmedQuery = searchQuery.trim().toLowerCase();
  const visibleTree = useMemo(
    () =>
      trimmedQuery
        ? filterTree(hierarchicalTree, trimmedQuery)
        : hierarchicalTree,
    [hierarchicalTree, trimmedQuery]
  );

  const fileCount = useMemo(
    () => (tree ?? []).filter((entry) => !entry.is_directory).length,
    [tree]
  );

  useEffect(() => {
    if (enabled) return;
    dragDepth.current = 0;
    setIsDragging(false);
    setSearchQuery("");
    setActionError(null);
    setIsCreatingFolder(false);
    setIsSubmittingFolder(false);
    setNewFolderName("");
    setSelectedEntry(null);
    setEntryToDelete(null);
  }, [enabled]);

  const uploadFiles = useCallback(
    async (fileArray: File[], targetPath: string) => {
      if (fileArray.length === 0) return;

      setIsUploading(true);
      setActionError(null);

      try {
        const firstFile = fileArray[0];
        if (
          fileArray.length === 1 &&
          firstFile &&
          firstFile.name.endsWith(".zip")
        ) {
          await uploadLibraryZip(targetPath, firstFile);
        } else {
          await uploadLibraryFiles(targetPath, fileArray);
        }
        void mutate();
        onChanges?.();
      } catch (err) {
        setActionError(
          err instanceof Error ? err.message : t("errors.uploadFailed")
        );
      } finally {
        setIsUploading(false);
      }
    },
    [mutate, onChanges, t]
  );

  const handleFileInputChange = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const files = event.target.files;
      if (!files || files.length === 0) return;
      const targetPath = uploadTargetPathRef.current;
      void uploadFiles(Array.from(files), targetPath).finally(() => {
        uploadTargetPathRef.current = "/";
        event.target.value = "";
      });
    },
    [uploadFiles]
  );

  const handleUploadToFolder = useCallback((folderPath: string) => {
    uploadTargetPathRef.current = folderPath;
    fileInputRef.current?.click();
  }, []);

  const handleDragEnter = useCallback((e: React.DragEvent) => {
    if (!e.dataTransfer.types.includes("Files")) return;
    e.preventDefault();
    dragDepth.current += 1;
    setIsDragging(true);
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    if (e.dataTransfer.types.includes("Files")) e.preventDefault();
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    dragDepth.current -= 1;
    if (dragDepth.current <= 0) {
      dragDepth.current = 0;
      setIsDragging(false);
    }
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      dragDepth.current = 0;
      setIsDragging(false);
      if (isUploading) return;
      const files = Array.from(e.dataTransfer.files);
      if (files.length > 0) void uploadFiles(files, "/");
    },
    [uploadFiles, isUploading]
  );

  const handleDeleteConfirm = useCallback(async () => {
    if (!entryToDelete) return;

    try {
      await deleteLibraryFile(entryToDelete.id);
      setActionError(null);
      void mutate();
      onChanges?.();
      setSelectedEntry(null);
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : t("errors.deleteFailed")
      );
    } finally {
      setEntryToDelete(null);
    }
  }, [entryToDelete, mutate, onChanges, t]);

  const cancelCreateFolder = useCallback(() => {
    if (isSubmittingFolder) return;
    setIsCreatingFolder(false);
    setNewFolderName("");
  }, [isSubmittingFolder]);

  const toggleCreateFolder = useCallback(() => {
    if (isCreatingFolder) {
      cancelCreateFolder();
      return;
    }
    setNewFolderName("");
    setIsCreatingFolder(true);
  }, [cancelCreateFolder, isCreatingFolder]);

  const handleCreateDirectory = useCallback(async () => {
    const name = newFolderName.trim();
    if (!name || isSubmittingFolder) return;

    setIsSubmittingFolder(true);
    try {
      await createLibraryDirectory({ name, parent_path: "/" });
      setActionError(null);
      void mutate();
      onChanges?.();
      setIsCreatingFolder(false);
      setNewFolderName("");
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : t("errors.createFolderFailed")
      );
    } finally {
      setIsSubmittingFolder(false);
    }
  }, [isSubmittingFolder, mutate, newFolderName, onChanges, t]);

  const isEmpty = hierarchicalTree.length === 0;
  const noMatches = !isEmpty && visibleTree.length === 0;

  return {
    actionError,
    cancelCreateFolder,
    entryToDelete,
    error,
    fileCount,
    fileInputRef,
    handleCreateDirectory,
    handleDeleteConfirm,
    handleDragEnter,
    handleDragLeave,
    handleDragOver,
    handleDrop,
    handleFileInputChange,
    handleUploadToFolder,
    hierarchicalTree,
    isCreatingFolder,
    isDragging,
    isEmpty,
    isLoading,
    isSubmittingFolder,
    isUploading,
    newFolderName,
    noMatches,
    searchQuery,
    selectedEntry,
    setEntryToDelete,
    setNewFolderName,
    setSearchQuery,
    setSelectedEntry,
    toggleCreateFolder,
    visibleTree,
  };
}

export type UserLibraryController = ReturnType<typeof useUserLibrary>;
