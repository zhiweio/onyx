"use client";

import { useMemo } from "react";
import { useTranslations } from "next-intl";
import type { ProjectFile } from "@/lib/projects/types";
import { UserFileStatus } from "@/lib/projects/types";
import { isImageFile } from "@/lib/utils";
import { cn } from "@opal/utils";
import { SvgFileText, SvgX, SvgSimpleLoader } from "@opal/icons";
import { FileThumbnail as ExtendFileThumbnail } from "@/sections/extend/file-thumbnail";
import { Interactive, Hoverable } from "@opal/core";
import { AttachmentItemLayout } from "@/layouts/general-layouts";
import { Spacer } from "@opal/components";

interface RemovableProps {
  onRemove?: () => void;
  children: React.ReactNode;
}

function Removable({ onRemove, children }: RemovableProps) {
  const t = useTranslations("cards");

  if (!onRemove) {
    return <>{children}</>;
  }

  return (
    <Hoverable.Root group="fileCard" width="fit">
      <div className="relative">
        <div
          className={cn(
            "absolute -start-2 -top-2 z-10",
            "pointer-events-none focus-within:pointer-events-auto"
          )}
        >
          <Hoverable.Item group="fileCard" variant="appear-on-hover">
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onRemove();
              }}
              title={t("file.remove.label")}
              aria-label={t("file.remove.label")}
              className={cn(
                "h-4 w-4",
                "flex items-center justify-center",
                "rounded-04 border border-border text-[11px]",
                "bg-background-neutral-inverted-01 text-text-inverted-05 shadow-xs",
                "pointer-events-auto",
                "hover:opacity-90"
              )}
            >
              <SvgX className="h-3 w-3 stroke-text-inverted-03" />
            </button>
          </Hoverable.Item>
        </div>
        {children}
      </div>
    </Hoverable.Root>
  );
}

interface FileThumbnailProps {
  className: string;
  label: string;
  onClick?: () => void;
  children: React.ReactNode;
}

/** Renders the thumbnail as a button only when it can be opened. */
function FileThumbnail({
  className,
  label,
  onClick,
  children,
}: FileThumbnailProps) {
  if (!onClick) return <div className={className}>{children}</div>;

  return (
    <button
      type="button"
      className={className}
      aria-label={label}
      onClick={onClick}
    >
      {children}
    </button>
  );
}

interface ImageFileCardProps {
  file: ProjectFile;
  imageUrl: string | null;
  removeFile?: (fileId: string) => void;
  onFileClick?: (file: ProjectFile) => void;
  isProcessing?: boolean;
  compact?: boolean;
}
function ImageFileCard({
  file,
  imageUrl,
  removeFile,
  onFileClick,
  isProcessing = false,
  compact = false,
}: ImageFileCardProps) {
  const sizeClass = compact ? "h-11 w-11" : "h-20 w-20";

  const doneUploading = String(file.status) !== UserFileStatus.UPLOADING;

  return (
    <Removable
      onRemove={
        removeFile && doneUploading ? () => removeFile(file.id) : undefined
      }
    >
      <FileThumbnail
        className={cn(
          sizeClass,
          "rounded-08 border border-border-01",
          isProcessing && "bg-background-neutral-02",
          onFileClick && !isProcessing && "cursor-pointer hover:opacity-90"
        )}
        label={file.name}
        onClick={
          onFileClick && !isProcessing ? () => onFileClick(file) : undefined
        }
      >
        <ExtendFileThumbnail
          file={{ name: file.name, type: file.file_type || "image" }}
          previewImageUrl={imageUrl}
          isLoading={!doneUploading || isProcessing}
          className={cn(sizeClass, "rounded-08")}
          previewClassName="h-full w-full object-cover rounded-08"
        />
      </FileThumbnail>
    </Removable>
  );
}

export interface FileCardProps {
  file: ProjectFile;
  removeFile?: (fileId: string) => void;
  hideProcessingState?: boolean;
  onFileClick?: (file: ProjectFile) => void;
  compactImages?: boolean;
}
export function FileCard({
  file,
  removeFile,
  hideProcessingState = false,
  onFileClick,
  compactImages = false,
}: FileCardProps) {
  const t = useTranslations("cards");
  const typeLabel = useMemo(() => {
    const name = String(file.name || "");
    const lastDotIndex = name.lastIndexOf(".");
    if (lastDotIndex <= 0 || lastDotIndex === name.length - 1) {
      return "";
    }
    return name.slice(lastDotIndex + 1).toUpperCase();
  }, [file.name]);

  const isImage = useMemo(() => {
    return isImageFile(file.name);
  }, [file.name]);

  const imageUrl = useMemo(() => {
    if (isImage && file.file_id) {
      return `/api/chat/file/${file.file_id}`;
    }
    return null;
  }, [isImage, file.file_id]);

  const isActuallyProcessing =
    String(file.status) === UserFileStatus.UPLOADING ||
    String(file.status) === UserFileStatus.PROCESSING;

  // When hideProcessingState is true, we treat processing files as completed for display purposes
  const isProcessing = hideProcessingState ? false : isActuallyProcessing;

  const doneUploading = String(file.status) !== UserFileStatus.UPLOADING;

  // For images, always show the larger preview layout (even while processing)
  if (isImage) {
    return (
      <ImageFileCard
        file={file}
        imageUrl={imageUrl}
        removeFile={removeFile}
        onFileClick={onFileClick}
        isProcessing={isProcessing}
        compact={compactImages}
      />
    );
  }

  return (
    <Removable
      onRemove={
        removeFile && doneUploading ? () => removeFile(file.id) : undefined
      }
    >
      <div className="min-w-0 max-w-48">
        <Interactive.Stateless
          onClick={
            onFileClick && !isProcessing ? () => onFileClick(file) : undefined
          }
        >
          <Interactive.Container border size="fit" width="full">
            <div className="flex items-center gap-2">
              <ExtendFileThumbnail
                file={{ name: file.name, type: file.file_type || typeLabel }}
                isLoading={isProcessing}
                className="size-10 shrink-0"
              />
              <AttachmentItemLayout
                icon={isProcessing ? SvgSimpleLoader : SvgFileText}
                title={file.name}
                description={
                  isProcessing
                    ? file.status === UserFileStatus.UPLOADING
                      ? t("file.uploading.description")
                      : t("file.processing.description")
                    : typeLabel
                }
              />
            </div>
            <Spacer orientation="horizontal" rem={0.5} />
          </Interactive.Container>
        </Interactive.Stateless>
      </div>
    </Removable>
  );
}

// Skeleton loading component for file cards
export function FileCardSkeleton() {
  return (
    <div className="min-w-[120px] max-w-[240px] h-11 rounded-08 bg-background-tint-02 animate-pulse" />
  );
}
