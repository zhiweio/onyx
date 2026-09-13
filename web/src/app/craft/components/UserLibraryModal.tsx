"use client";

import { useState, useCallback, useRef, useMemo, useEffect } from "react";
import { useTranslations } from "next-intl";
import { useFocusOnMount } from "@opal/hooks";
import useSWR from "swr";
import { SWR_KEYS } from "@/lib/swr-keys";
import {
  fetchLibraryTree,
  uploadLibraryFiles,
  uploadLibraryZip,
  createLibraryDirectory,
  deleteLibraryFile,
} from "@/app/craft/services/apiServices";
import { LibraryEntry } from "@/app/craft/types/user-library";
import { Modal } from "@opal/components";
import { cn } from "@opal/utils";
import {
  SvgFolder,
  SvgUploadCloud,
  SvgTrash,
  SvgFolderPlus,
} from "@opal/icons";
import { Button, InputTypeIn, Text } from "@opal/components";
import { Section } from "@/layouts/general-layouts";

import { ConfirmEntityModal } from "@/sections/modals/ConfirmEntityModal";
import { FileSystem } from "@/sections/extend/file-system";
import { FileUpload } from "@/sections/extend/file-upload";
import { flattenLibraryTree } from "@/sections/document-preview/FileSystemAdapter";

/**
 * Build a hierarchical tree from a flat list of library entries.
 * Entries have paths like "user_library/test" or "user_library/test/file.pdf"
 */
function buildTreeFromFlatList(flatList: LibraryEntry[]): LibraryEntry[] {
  // Create a map of path -> entry (with children array initialized)
  const pathToEntry = new Map<string, LibraryEntry>();

  // First pass: create entries with empty children arrays
  for (const entry of flatList) {
    pathToEntry.set(entry.path, { ...entry, children: [] });
  }

  // Second pass: build parent-child relationships
  const rootEntries: LibraryEntry[] = [];

  for (const entry of flatList) {
    const entryWithChildren = pathToEntry.get(entry.path)!;

    // Find parent path by removing the last segment
    const pathParts = entry.path.split("/");
    pathParts.pop(); // Remove last segment (filename or folder name)
    const parentPath = pathParts.join("/");

    const parent = pathToEntry.get(parentPath);
    if (parent && parent.children) {
      parent.children.push(entryWithChildren);
    } else {
      // No parent found, this is a root-level entry
      rootEntries.push(entryWithChildren);
    }
  }

  return rootEntries;
}

/** Keep entries whose name matches, plus folders with any matching descendant. */
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

function findLibraryEntry(
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

interface UserLibraryModalProps {
  open: boolean;
  onClose: () => void;
  onChanges?: () => void; // Called when files are uploaded or deleted
}

export default function UserLibraryModal({
  open,
  onClose,
  onChanges,
}: UserLibraryModalProps) {
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
  // dragenter/dragleave fire for every child element; count depth so the
  // overlay only clears when the cursor truly leaves the drop region.
  const dragDepth = useRef(0);

  // Fetch library tree
  const {
    data: tree,
    error,
    isLoading,
    mutate,
  } = useSWR(open ? SWR_KEYS.buildUserLibraryTree : null, fetchLibraryTree, {
    revalidateOnFocus: false,
  });

  // Build hierarchical tree from flat list
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

  // Reset transient state when the modal closes, so a drag interrupted by a
  // close doesn't leave the overlay stuck and a stale search doesn't hide
  // files on reopen.
  useEffect(() => {
    if (!open) {
      dragDepth.current = 0;
      setIsDragging(false);
      setSearchQuery("");
      setActionError(null);
      setIsCreatingFolder(false);
      setIsSubmittingFolder(false);
      setNewFolderName("");
    }
  }, [open]);

  const uploadFiles = useCallback(
    async (fileArray: File[], targetPath: string) => {
      if (fileArray.length === 0) return;

      setIsUploading(true);
      setActionError(null);

      try {
        // A lone .zip is expanded server-side; everything else uploads as-is.
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
        mutate();
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
      mutate();
      onChanges?.();
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
      await mutate();
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

  return (
    <>
      <Modal open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
        <Modal.Content
          width="sm"
          height="fit"
          preventAccidentalClose={false}
          onEscapeKeyDown={(event) => {
            if (!isCreatingFolder) return;
            event.preventDefault();
            cancelCreateFolder();
          }}
        >
          <Modal.Header
            icon={SvgFolder}
            title={t("modal.title")}
            description={t("modal.description")}
            onClose={onClose}
          >
            <Section flexDirection="row" gap={2}>
              <InputTypeIn
                placeholder={t("search.placeholder")}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                searchIcon
                autoComplete="off"
              />
              <Button
                prominence="secondary"
                icon={SvgFolderPlus}
                onClick={toggleCreateFolder}
                tooltip={t("newFolder.label")}
                aria-label={t("newFolder.label")}
                aria-expanded={isCreatingFolder}
              />
              <Button
                icon={SvgUploadCloud}
                disabled={isUploading}
                onClick={() => handleUploadToFolder("/")}
              >
                {isUploading ? t("upload.uploadingButton") : t("upload.button")}
              </Button>
            </Section>
          </Modal.Header>
          <Modal.Body>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="hidden"
              onChange={handleFileInputChange}
              disabled={isUploading}
            />

            <div className="flex w-full flex-col gap-3">
              {isCreatingFolder && (
                <NewFolderPanel
                  name={newFolderName}
                  isSubmitting={isSubmittingFolder}
                  onNameChange={setNewFolderName}
                  onCancel={cancelCreateFolder}
                  onCreate={handleCreateDirectory}
                />
              )}

              {actionError && (
                <div className="rounded-8 border border-status-error-02 bg-status-error-01 px-3 py-2">
                  <Text font="secondary-body" color="status-error-05">
                    {actionError}
                  </Text>
                </div>
              )}

              {/* Drop region — accepts file drops in both empty and populated states */}
              <div
                className="relative"
                onDragEnter={handleDragEnter}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
              >
                {isLoading ? (
                  <div className="flex items-center justify-center py-12">
                    <Text font="secondary-body" color="text-03">
                      {t("loading.label")}
                    </Text>
                  </div>
                ) : error ? (
                  <div className="flex items-center justify-center py-12">
                    <Text font="secondary-body" color="status-error-05">
                      {t("errors.loadFailed")}
                    </Text>
                  </div>
                ) : (
                  <div className="flex flex-col gap-3">
                    <FileUpload
                      showBorderBeam={false}
                      showFileList={false}
                      title={t("upload.dropOverlay")}
                      description={t("modal.description")}
                      onFilesAccepted={(files) => void uploadFiles(files, "/")}
                    />
                    {isEmpty ? (
                      <UploadDropzone
                        onClick={() => handleUploadToFolder("/")}
                        active={isDragging}
                      />
                    ) : noMatches ? (
                      <div className="flex items-center justify-center py-12">
                        <Text font="secondary-body" color="text-03">
                          {t("search.noResults")}
                        </Text>
                      </div>
                    ) : (
                      <div className="flex h-[22rem] min-h-0 flex-col gap-2">
                        {selectedEntry && (
                          <div className="flex items-center justify-end">
                            <Button
                              variant="danger"
                              prominence="tertiary"
                              size="sm"
                              icon={SvgTrash}
                              onClick={() => setEntryToDelete(selectedEntry)}
                            >
                              {t("tree.deleteTooltip")}
                            </Button>
                          </div>
                        )}
                        <FileSystem
                          className="h-full"
                          items={flattenLibraryTree(visibleTree)}
                          title={t("modal.title")}
                          defaultView="list"
                          onFileOpen={() => undefined}
                          onSelectionChange={(item) => {
                            if (!item) {
                              setSelectedEntry(null);
                              return;
                            }
                            setSelectedEntry(
                              findLibraryEntry(visibleTree, item.path)
                            );
                          }}
                        />
                      </div>
                    )}
                  </div>
                )}

                {/* Drag overlay — consistent feedback regardless of state */}
                {isDragging && (
                  <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center rounded-12 border-2 border-dashed border-action-selection-04 bg-action-selection-01/90">
                    <Text font="main-ui-action" color="text-05">
                      {t("upload.dropOverlay")}
                    </Text>
                  </div>
                )}
              </div>
            </div>
          </Modal.Body>

          <Modal.Footer>
            <Button prominence="secondary" onClick={onClose}>
              {t("modal.doneButton")}
            </Button>
          </Modal.Footer>
        </Modal.Content>
      </Modal>

      {/* Delete confirmation modal */}
      {entryToDelete && (
        <ConfirmEntityModal
          danger
          entityType={
            entryToDelete.is_directory
              ? t("delete.entityTypeFolder")
              : t("delete.entityTypeFile")
          }
          entityName={entryToDelete.name}
          action={t("delete.action")}
          actionButtonText={t("delete.button")}
          additionalDetails={
            entryToDelete.is_directory
              ? t("delete.folderDetails")
              : t("delete.fileDetails")
          }
          onClose={() => setEntryToDelete(null)}
          onSubmit={handleDeleteConfirm}
        />
      )}
    </>
  );
}

interface NewFolderPanelProps {
  name: string;
  isSubmitting: boolean;
  onNameChange: (name: string) => void;
  onCancel: () => void;
  onCreate: () => void | Promise<void>;
}

function NewFolderPanel({
  name,
  isSubmitting,
  onNameChange,
  onCancel,
  onCreate,
}: NewFolderPanelProps) {
  const t = useTranslations("craft.userLibrary");
  const focusOnMount = useFocusOnMount<HTMLInputElement>();
  const canCreate = name.trim().length > 0 && !isSubmitting;

  return (
    <form
      aria-label={t("newFolder.label")}
      onSubmit={(event) => {
        event.preventDefault();
        if (canCreate) void onCreate();
      }}
      className="w-full"
    >
      <Section
        flexDirection="column"
        alignItems="stretch"
        justifyContent="start"
        gap={2}
        padding={3}
        height="auto"
        className="rounded-12 border border-border-02 bg-background-tint-02"
      >
        <Text font="secondary-action" color="text-04">
          {t("newFolder.nameLabel")}
        </Text>
        <Section
          flexDirection="row"
          alignItems="center"
          justifyContent="start"
          gap={2}
          height="auto"
        >
          <div className="min-w-0 flex-1">
            <InputTypeIn
              ref={focusOnMount}
              value={name}
              onChange={(event) => onNameChange(event.target.value)}
              placeholder={t("newFolder.namePlaceholder")}
              autoComplete="off"
              variant={isSubmitting ? "disabled" : "primary"}
            />
          </div>
          <Button
            type="button"
            prominence="secondary"
            disabled={isSubmitting}
            onClick={onCancel}
          >
            {t("newFolder.cancelButton")}
          </Button>
          <Button type="submit" disabled={!canCreate}>
            {t("newFolder.createButton")}
          </Button>
        </Section>
      </Section>
    </form>
  );
}

interface UploadDropzoneProps {
  onClick: () => void;
  active: boolean;
}

function UploadDropzone({ onClick, active }: UploadDropzoneProps) {
  const t = useTranslations("craft.userLibrary");
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === " " || e.key === "Enter") {
          e.preventDefault();
          onClick();
        }
      }}
      className={cn(
        "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-12 border border-dashed px-6 py-10 text-center transition-colors",
        active
          ? "border-action-selection-04 bg-action-selection-01"
          : "border-border-03 bg-background-tint-02 hover:border-action-selection-04 hover:bg-action-selection-01"
      )}
    >
      <SvgUploadCloud size={28} className="stroke-text-03" />
      <Text font="main-ui-action" color="text-04">
        {t("dropzone.title")}
      </Text>
      <Text font="secondary-body" color="text-03">
        {t("dropzone.formats")}
      </Text>
    </div>
  );
}
