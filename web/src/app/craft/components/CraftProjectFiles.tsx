"use client";

import { useCallback, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { useDropzone } from "react-dropzone";
import {
  Button,
  Card,
  InputTypeIn,
  LineItemButton,
  Text,
} from "@opal/components";
import { ContentAction, toast } from "@opal/layouts";
import {
  SvgDownload,
  SvgFile,
  SvgFileBraces,
  SvgFileChartPie,
  SvgFileText,
  SvgFolder,
  SvgTrash,
  SvgUploadCloud,
} from "@opal/icons";
import type { IconFunctionComponent } from "@opal/types";
import { cn } from "@opal/utils";
import { Section } from "@/layouts/general-layouts";
import CraftProjectFilePreview from "@/app/craft/components/CraftProjectFilePreview";
import {
  craftProjectFileUrl,
  deleteCraftProjectFile,
  uploadCraftProjectFile,
} from "@/lib/craft-projects/api";
import {
  fileExtension,
  fileKind,
  groupProjectFilesByFolder,
  type CraftProjectFileKind,
} from "@/lib/craft-projects/display";
import type { CraftProjectFile } from "@/lib/craft-projects/types";
import { formatBytes } from "@/lib/utils";

const FILE_KIND_ICON: Record<CraftProjectFileKind, IconFunctionComponent> = {
  markdown: SvgFileText,
  table: SvgFileChartPie,
  json: SvgFileBraces,
  other: SvgFile,
};

interface CraftProjectFilesProps {
  projectId: string;
  files: CraftProjectFile[];
  onChanged: () => Promise<void> | void;
}

function fileDescription(
  file: CraftProjectFile,
  t: ReturnType<typeof useTranslations>
): string {
  const path = file.path.replace(/\\/g, "/").replace(/^\//, "");
  const parts: string[] = [];
  if (path && path !== file.name) {
    parts.push(path);
  }
  parts.push(
    file.source === "session_output"
      ? t("detail.sourceOutput.label")
      : t("detail.sourceUpload.label")
  );
  if (file.size_bytes != null) {
    parts.push(formatBytes(file.size_bytes, 1));
  }
  return parts.join(" · ");
}

export default function CraftProjectFiles({
  projectId,
  files,
  onChanged,
}: CraftProjectFilesProps) {
  const t = useTranslations("craft.projects");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  const visibleFiles = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) {
      return files;
    }
    return files.filter((item) => {
      const haystack = `${item.name} ${item.path}`.toLowerCase();
      return haystack.includes(needle);
    });
  }, [files, query]);

  const groups = useMemo(
    () => groupProjectFilesByFolder(visibleFiles),
    [visibleFiles]
  );
  const showFolderHeaders =
    groups.length > 1 || (groups[0] !== undefined && groups[0].folder !== "");
  const selected =
    files.find((item) => item.id === selectedId) ??
    visibleFiles.find((item) => item.id === selectedId) ??
    null;

  const onDrop = useCallback(
    async (accepted: File[]) => {
      const file = accepted[0];
      if (!file) {
        return;
      }
      setUploading(true);
      try {
        await uploadCraftProjectFile(projectId, file);
        await onChanged();
        toast.success(t("toasts.uploaded.message"));
      } catch (uploadError) {
        toast.error(
          uploadError instanceof Error
            ? uploadError.message
            : t("toasts.uploadFailed.message")
        );
      } finally {
        setUploading(false);
      }
    },
    [onChanged, projectId, t]
  );

  const { getRootProps, getInputProps, open, isDragActive } = useDropzone({
    disabled: uploading,
    multiple: false,
    noClick: true,
    noKeyboard: true,
    onDropAccepted: onDrop,
  });

  async function handleRemoveFile(file: CraftProjectFile) {
    try {
      await deleteCraftProjectFile(projectId, file.id);
      if (selectedId === file.id) {
        setSelectedId(null);
      }
      await onChanged();
      toast.success(t("toasts.fileDeleted.message"));
    } catch (removeError) {
      toast.error(
        removeError instanceof Error
          ? removeError.message
          : t("toasts.deleteFailed.message")
      );
    }
  }

  return (
    <>
      <Card border="solid" rounding={4} padding={4}>
        <Section
          gap={3}
          alignItems="stretch"
          justifyContent="start"
          height="auto"
        >
          <ContentAction
            icon={SvgFolder}
            title={t("detail.files.title")}
            description={t("card.fileCount.label", { count: files.length })}
            sizePreset="main-ui"
            variant="section"
            width="full"
            rightChildren={
              <Button
                prominence="secondary"
                icon={SvgUploadCloud}
                disabled={uploading}
                onClick={open}
              >
                {t("detail.upload.label")}
              </Button>
            }
          />
          <div
            {...getRootProps()}
            className={cn(
              "rounded-12 p-2 flex flex-col gap-2 w-full min-w-0",
              isDragActive
                ? "border border-dashed border-border-03 bg-background-tint-02"
                : files.length === 0
                  ? "bg-background-tint-00"
                  : "border border-border-01"
            )}
          >
            <input {...getInputProps()} />
            {files.length === 0 ? (
              <Text font="secondary-body" color="text-03">
                {isDragActive
                  ? t("detail.dropHint.description")
                  : t("detail.emptyFiles.description")}
              </Text>
            ) : (
              <div className="flex w-full min-w-0 flex-col gap-2">
                <InputTypeIn
                  searchIcon
                  placeholder={t("detail.fileSearch.placeholder")}
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                />
                {visibleFiles.length === 0 ? (
                  <Text font="secondary-body" color="text-03">
                    {t("detail.noMatchingFiles.description")}
                  </Text>
                ) : (
                  <div className="flex w-full min-w-0 flex-col gap-2">
                    {groups.map((group) => (
                      <div
                        key={group.folder || "root"}
                        className="flex w-full min-w-0 flex-col gap-0.5"
                      >
                        {showFolderHeaders && (
                          <Text font="secondary-body" color="text-03">
                            {group.folder || t("detail.fileFolder.root")}
                          </Text>
                        )}
                        {group.files.map((file) => {
                          const ext = fileExtension(file.name);
                          return (
                            <LineItemButton
                              key={file.id}
                              sizePreset="main-ui"
                              variant="section"
                              rounding={2}
                              width="full"
                              icon={FILE_KIND_ICON[fileKind(file)]}
                              title={file.name}
                              titleMaxLines={1}
                              description={fileDescription(file, t)}
                              descriptionMaxLines={1}
                              tooltip={file.path || file.name}
                              tag={
                                ext
                                  ? {
                                      color: "gray",
                                      title: ext.toUpperCase(),
                                    }
                                  : undefined
                              }
                              onClick={() => setSelectedId(file.id)}
                              rightChildren={
                                <div className="flex items-center gap-1">
                                  <Button
                                    prominence="tertiary"
                                    size="sm"
                                    icon={SvgDownload}
                                    tooltip={t("detail.download.tooltip")}
                                    aria-label={t("detail.download.tooltip")}
                                    href={craftProjectFileUrl(
                                      projectId,
                                      file.id
                                    )}
                                  />
                                  <Button
                                    prominence="tertiary"
                                    size="sm"
                                    icon={SvgTrash}
                                    tooltip={t("detail.removeFile.tooltip")}
                                    aria-label={t("detail.removeFile.tooltip")}
                                    onClick={() => void handleRemoveFile(file)}
                                  />
                                </div>
                              }
                            />
                          );
                        })}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </Section>
      </Card>
      {selected && (
        <CraftProjectFilePreview
          projectId={projectId}
          files={
            visibleFiles.some((item) => item.id === selected.id)
              ? visibleFiles
              : files
          }
          file={selected}
          onClose={() => setSelectedId(null)}
          onSelect={(item) => setSelectedId(item.id)}
          onChanged={onChanged}
        />
      )}
    </>
  );
}
