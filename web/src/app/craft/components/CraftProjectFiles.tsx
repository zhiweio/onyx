"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { Button, Card, Text } from "@opal/components";
import { ContentAction, toast } from "@opal/layouts";
import { SvgFolder, SvgUploadCloud } from "@opal/icons";
import { Section } from "@/layouts/general-layouts";
import CraftProjectFilePreview from "@/app/craft/components/CraftProjectFilePreview";
import {
  craftProjectFileUrl,
  uploadCraftProjectFile,
} from "@/lib/craft-projects/api";

import type { CraftProjectFile } from "@/lib/craft-projects/types";
import { FileUpload } from "@/sections/extend/file-upload";
import {
  FileSystem,
  type FileSystemFileItem,
  type FileSystemItem,
} from "@/sections/extend/file-system";
import {
  craftFilesToItems,
  fileSystemFileId,
} from "@/sections/document-preview/FileSystemAdapter";

interface CraftProjectFilesProps {
  projectId: string;
  files: CraftProjectFile[];
  onChanged: () => Promise<void> | void;
}

export default function CraftProjectFiles({
  projectId,
  files,
  onChanged,
}: CraftProjectFilesProps) {
  const t = useTranslations("craft.projects");
  const inputRef = useRef<HTMLInputElement>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);

  const items = useMemo(
    () =>
      craftFilesToItems(files, (file) =>
        craftProjectFileUrl(projectId, file.id)
      ),
    [files, projectId]
  );

  const selected = files.find((item) => item.id === selectedId) ?? null;

  const matchProjectFile = useCallback(
    (item: FileSystemFileItem | FileSystemItem) => {
      if (item.kind !== "file") {
        return undefined;
      }
      const id = fileSystemFileId(item);
      return (
        files.find((entry) => entry.id === id) ??
        files.find(
          (entry) =>
            (entry.path || entry.name).replace(/^\/+/, "") ===
              item.path.replace(/^\/+/, "") || entry.name === item.name
        )
      );
    },
    [files]
  );

  const handleUpload = useCallback(
    async (accepted: File[]) => {
      const file = accepted[0];
      if (!file) return;
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
              <div className="flex items-center gap-2">
                {uploading ? (
                  <Text font="secondary-body" color="text-03">
                    {t("detail.upload.label")}
                  </Text>
                ) : null}
                {files.length > 0 ? (
                  <Button
                    prominence="tertiary"
                    size="sm"
                    icon={SvgUploadCloud}
                    disabled={uploading}
                    onClick={() => inputRef.current?.click()}
                  >
                    {t("detail.upload.label")}
                  </Button>
                ) : null}
              </div>
            }
          />
          <input
            ref={inputRef}
            type="file"
            className="hidden"
            onChange={(event) => {
              const next = event.target.files
                ? Array.from(event.target.files)
                : [];
              if (next.length > 0) {
                void handleUpload(next);
              }
              event.currentTarget.value = "";
            }}
          />
          {files.length === 0 ? (
            <FileUpload
              multiple={false}
              showBorderBeam={false}
              showFileList={false}
              title={t("detail.dropHint.description")}
              description={t("detail.emptyFiles.description")}
              onFilesAccepted={(next) => void handleUpload(next)}
            />
          ) : (
            <div
              className="relative h-[28rem] min-h-0 w-full overflow-hidden"
              onDragEnter={(event) => {
                event.preventDefault();
                setDragging(true);
              }}
              onDragOver={(event) => event.preventDefault()}
              onDragLeave={(event) => {
                if (
                  event.currentTarget.contains(event.relatedTarget as Node)
                ) {
                  return;
                }
                setDragging(false);
              }}
              onDrop={(event) => {
                event.preventDefault();
                setDragging(false);
                const next = Array.from(event.dataTransfer.files);
                if (next.length > 0) {
                  void handleUpload(next);
                }
              }}
            >
              {dragging ? (
                <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center rounded-xl border-2 border-dashed border-action-selection-04 bg-action-selection-01/90">
                  <Text font="main-ui-action" color="text-05">
                    {t("detail.dropHint.description")}
                  </Text>
                </div>
              ) : null}
              <FileSystem
                className="h-full"
                items={items}
                title={t("detail.files.title")}
                defaultView="list"
                onFileOpen={(file) => {
                  const match = matchProjectFile(file);
                  if (match) setSelectedId(match.id);
                }}
                onSelectionChange={(item) => {
                  if (!item || item.kind !== "file") return;
                  const match = matchProjectFile(item);
                  if (match) setSelectedId(match.id);
                }}
                getFileUrl={(file) => file.url ?? ""}
              />
            </div>
          )}
        </Section>
      </Card>
      {selected && (
        <CraftProjectFilePreview
          projectId={projectId}
          files={files}
          file={selected}
          onClose={() => setSelectedId(null)}
          onSelect={(item) => setSelectedId(item.id)}
          onChanged={onChanged}
        />
      )}
    </>
  );
}
