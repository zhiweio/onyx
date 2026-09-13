"use client";

import { useTranslations } from "next-intl";
import { useFocusOnMount } from "@opal/hooks";
import { cn } from "@opal/utils";
import { SvgFolderPlus, SvgTrash, SvgUploadCloud } from "@opal/icons";
import { Button, InputTypeIn, Text } from "@opal/components";
import { Section } from "@/layouts/general-layouts";
import { ConfirmEntityModal } from "@/sections/modals/ConfirmEntityModal";
import { FileSystem } from "@/sections/extend/file-system";
import { flattenLibraryTree } from "@/sections/document-preview/FileSystemAdapter";
import {
  findLibraryEntry,
  libraryEntryToApiPath,
  type UserLibraryController,
} from "@/app/craft/hooks/useUserLibrary";

export interface UserLibraryActionsProps {
  library: UserLibraryController;
}

export function UserLibraryActions({ library }: UserLibraryActionsProps) {
  const t = useTranslations("craft.userLibrary");
  return (
    <>
      <Button
        prominence="secondary"
        icon={SvgFolderPlus}
        onClick={library.toggleCreateFolder}
        tooltip={t("newFolder.label")}
        aria-label={t("newFolder.label")}
        aria-expanded={library.isCreatingFolder}
      />
      <Button
        icon={SvgUploadCloud}
        disabled={library.isUploading}
        onClick={() => library.handleUploadToFolder("/")}
      >
        {library.isUploading ? t("upload.uploadingButton") : t("upload.button")}
      </Button>
    </>
  );
}

export interface UserLibraryManagerProps {
  library: UserLibraryController;
  /** Taller list for the settings page. */
  variant?: "page" | "modal";
}

export function UserLibraryManager({
  library,
  variant = "modal",
}: UserLibraryManagerProps) {
  const t = useTranslations("craft.userLibrary");
  const listHeightClass =
    variant === "page"
      ? "h-[min(40rem,calc(100dvh-22rem))] min-h-[28rem]"
      : "h-[22rem]";

  return (
    <>
      <input
        ref={library.fileInputRef}
        type="file"
        multiple
        className="hidden"
        onChange={library.handleFileInputChange}
        disabled={library.isUploading}
      />

      <div className="flex w-full flex-col gap-3">
        {library.isCreatingFolder && (
          <NewFolderPanel
            name={library.newFolderName}
            isSubmitting={library.isSubmittingFolder}
            onNameChange={library.setNewFolderName}
            onCancel={library.cancelCreateFolder}
            onCreate={library.handleCreateDirectory}
          />
        )}

        {library.actionError && (
          <div className="rounded-8 border border-status-error-02 bg-status-error-01 px-3 py-2">
            <Text font="secondary-body" color="status-error-05">
              {library.actionError}
            </Text>
          </div>
        )}

        <div
          className="relative"
          onDragEnter={library.handleDragEnter}
          onDragOver={library.handleDragOver}
          onDragLeave={library.handleDragLeave}
          onDrop={library.handleDrop}
        >
          {library.isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Text font="secondary-body" color="text-03">
                {t("loading.label")}
              </Text>
            </div>
          ) : library.error ? (
            <div className="flex items-center justify-center py-12">
              <Text font="secondary-body" color="status-error-05">
                {t("errors.loadFailed")}
              </Text>
            </div>
          ) : library.isEmpty ? (
            <UploadDropzone
              onClick={() => library.handleUploadToFolder("/")}
              active={library.isDragging}
              disabled={library.isUploading}
            />
          ) : library.noMatches ? (
            <div className="flex items-center justify-center py-12">
              <Text font="secondary-body" color="text-03">
                {t("search.noResults")}
              </Text>
            </div>
          ) : (
            <div className={cn("flex min-h-0 flex-col gap-2", listHeightClass)}>
              {library.selectedEntry && (
                <div className="flex items-center justify-end gap-2">
                  {library.selectedEntry.is_directory && (
                    <Button
                      prominence="secondary"
                      size="sm"
                      icon={SvgUploadCloud}
                      onClick={() =>
                        library.handleUploadToFolder(
                          libraryEntryToApiPath(library.selectedEntry!.path)
                        )
                      }
                    >
                      {t("tree.uploadToFolderTooltip")}
                    </Button>
                  )}
                  <Button
                    variant="danger"
                    prominence="tertiary"
                    size="sm"
                    icon={SvgTrash}
                    onClick={() =>
                      library.setEntryToDelete(library.selectedEntry)
                    }
                  >
                    {t("tree.deleteTooltip")}
                  </Button>
                </div>
              )}
              <FileSystem
                className="h-full"
                items={flattenLibraryTree(library.visibleTree)}
                title={t("modal.title")}
                defaultView="list"
                onFileOpen={() => undefined}
                onSelectionChange={(item) => {
                  if (!item) {
                    library.setSelectedEntry(null);
                    return;
                  }
                  library.setSelectedEntry(
                    findLibraryEntry(library.visibleTree, item.path)
                  );
                }}
              />
            </div>
          )}

          {library.isDragging && (
            <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center rounded-12 border-2 border-dashed border-action-selection-04 bg-action-selection-01/90">
              <Text font="main-ui-action" color="text-05">
                {t("upload.dropOverlay")}
              </Text>
            </div>
          )}
        </div>
      </div>

      {library.entryToDelete && (
        <ConfirmEntityModal
          danger
          entityType={
            library.entryToDelete.is_directory
              ? t("delete.entityTypeFolder")
              : t("delete.entityTypeFile")
          }
          entityName={library.entryToDelete.name}
          action={t("delete.action")}
          actionButtonText={t("delete.button")}
          additionalDetails={
            library.entryToDelete.is_directory
              ? t("delete.folderDetails")
              : t("delete.fileDetails")
          }
          onClose={() => library.setEntryToDelete(null)}
          onSubmit={library.handleDeleteConfirm}
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
  disabled?: boolean;
}

function UploadDropzone({
  onClick,
  active,
  disabled = false,
}: UploadDropzoneProps) {
  const t = useTranslations("craft.userLibrary");
  return (
    <div
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-label={t("dropzone.title")}
      aria-disabled={disabled}
      onClick={() => {
        if (!disabled) onClick();
      }}
      onKeyDown={(e) => {
        if (disabled) return;
        if (e.key === " " || e.key === "Enter") {
          e.preventDefault();
          onClick();
        }
      }}
      className={cn(
        "flex flex-col items-center justify-center gap-2 rounded-12 border border-dashed px-6 py-10 text-center transition-colors",
        disabled
          ? "cursor-not-allowed border-border-03 bg-background-tint-02 opacity-60"
          : active
            ? "cursor-pointer border-action-selection-04 bg-action-selection-01"
            : "cursor-pointer border-border-03 bg-background-tint-02 hover:border-action-selection-04 hover:bg-action-selection-01"
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
