"use client";

import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { Button, Modal, Text } from "@opal/components";
import {
  SvgChevronLeft,
  SvgChevronRight,
  SvgDownload,
  SvgFile,
  SvgTrash,
} from "@opal/icons";
import { Section, toast } from "@opal/layouts";
import ImagePreview from "@/app/craft/components/output-panel/ImagePreview";
import MarkdownFilePreview from "@/app/craft/components/output-panel/MarkdownFilePreview";
import {
  craftProjectFileUrl,
  deleteCraftProjectFile,
  fetchCraftProjectFileContent,
  type CraftProjectFilePreviewPayload,
} from "@/lib/craft-projects/api";
import {
  formatProjectFileText,
  isProjectDocumentPreviewKind,
  projectFilePreviewKind,
} from "@/lib/craft-projects/display";
import type { CraftProjectFile } from "@/lib/craft-projects/types";
import {
  DocumentPreview,
  resolveDocumentPreviewMode,
  saveCraftProjectFileBytes,
} from "@/sections/document-preview";
import { filePreviewKind } from "@/sections/document-preview/filePreviewKind";
import UnsavedChangesModal from "@/sections/modals/UnsavedChangesModal";

interface CraftProjectFilePreviewProps {
  projectId: string;
  files: CraftProjectFile[];
  file: CraftProjectFile;
  onClose: () => void;
  onSelect: (file: CraftProjectFile) => void;
  onChanged: () => Promise<void> | void;
}

export default function CraftProjectFilePreview({
  projectId,
  files,
  file,
  onClose,
  onSelect,
  onChanged,
}: CraftProjectFilePreviewProps) {
  const t = useTranslations("craft.projects");
  const previewT = useTranslations("craft.filePreview");
  const kind = projectFilePreviewKind(file);
  const previewMode = resolveDocumentPreviewMode(
    "craft-project",
    filePreviewKind(file.name, file.mime_type)
  );
  const [payload, setPayload] = useState<CraftProjectFilePreviewPayload | null>(
    null
  );
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(
    kind !== "unsupported" && !isProjectDocumentPreviewKind(kind)
  );
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [removing, setRemoving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [confirmClose, setConfirmClose] = useState(false);

  const index = files.findIndex((item) => item.id === file.id);
  const previous = index > 0 ? files[index - 1] : undefined;
  const next =
    index >= 0 && index < files.length - 1 ? files[index + 1] : undefined;

  useEffect(() => {
    let cancelled = false;
    const previewKind = projectFilePreviewKind(file);
    if (previewKind === "unsupported") {
      setPayload({ status: "unsupported" });
      setError(null);
      setLoading(false);
      setImageUrl(null);
      return;
    }
    if (isProjectDocumentPreviewKind(previewKind)) {
      setPayload({ status: "document" });
      setError(null);
      setLoading(false);
      setImageUrl(null);
      setDirty(false);
      setConfirmClose(false);
      return;
    }

    setLoading(true);
    setError(null);
    setPayload(null);
    void fetchCraftProjectFileContent(projectId, file)
      .then((result) => {
        if (cancelled) {
          return;
        }
        setPayload(result);
        setLoading(false);
      })
      .catch((loadError: unknown) => {
        if (cancelled) {
          return;
        }
        setError(
          loadError instanceof Error
            ? loadError.message
            : previewT("error.title")
        );
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [file, previewT, projectId]);

  useEffect(() => {
    if (payload?.status !== "image") {
      setImageUrl(null);
      return;
    }
    const url = URL.createObjectURL(payload.blob);
    setImageUrl(url);
    return () => {
      URL.revokeObjectURL(url);
    };
  }, [payload]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "ArrowLeft" && previous) {
        event.preventDefault();
        onSelect(previous);
      }
      if (event.key === "ArrowRight" && next) {
        event.preventDefault();
        onSelect(next);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [next, onSelect, previous]);

  const text = useMemo(() => {
    if (payload?.status !== "text") {
      return "";
    }
    return formatProjectFileText(payload.text, kind);
  }, [kind, payload]);

  async function handleDelete() {
    setRemoving(true);
    const currentIndex = files.findIndex((item) => item.id === file.id);
    const fallback = files[currentIndex + 1] ?? files[currentIndex - 1] ?? null;
    try {
      await deleteCraftProjectFile(projectId, file.id);
      await onChanged();
      toast.success(t("toasts.fileDeleted.message"));
      if (fallback) {
        onSelect(fallback);
      } else {
        onClose();
      }
    } catch (removeError) {
      toast.error(
        removeError instanceof Error
          ? removeError.message
          : t("toasts.deleteFailed.message")
      );
    } finally {
      setRemoving(false);
    }
  }

  function requestClose() {
    if (dirty) {
      setConfirmClose(true);
      return;
    }
    onClose();
  }

  return (
    <Modal
      open
      onOpenChange={(open) => {
        if (!open) {
          requestClose();
        }
      }}
    >
      <Modal.Content
        width="full"
        height="full"
        preventAccidentalClose={false}
        data-testid="craft-project-file-preview"
      >
        <Modal.Header
          icon={SvgFile}
          title={file.name}
          description={file.path || file.name}
          onClose={requestClose}
        >
          <div className="flex flex-wrap items-center gap-1 px-2 pb-1">
            <Button
              prominence="tertiary"
              size="sm"
              icon={SvgChevronLeft}
              disabled={!previous}
              tooltip={t("detail.preview.previous")}
              aria-label={t("detail.preview.previous")}
              onClick={() => previous && onSelect(previous)}
            />
            <Button
              prominence="tertiary"
              size="sm"
              icon={SvgChevronRight}
              disabled={!next}
              tooltip={t("detail.preview.next")}
              aria-label={t("detail.preview.next")}
              onClick={() => next && onSelect(next)}
            />
            <Button
              prominence="tertiary"
              size="sm"
              icon={SvgDownload}
              tooltip={t("detail.download.tooltip")}
              aria-label={t("detail.download.tooltip")}
              href={craftProjectFileUrl(projectId, file.id)}
            />
            <Button
              prominence="tertiary"
              size="sm"
              icon={SvgTrash}
              disabled={removing}
              tooltip={t("detail.removeFile.tooltip")}
              aria-label={t("detail.removeFile.tooltip")}
              onClick={() => void handleDelete()}
            />
          </div>
        </Modal.Header>
        <Modal.Body padding={0} gap={0} alignItems="stretch" height="full">
          <div className="flex h-full min-h-0 w-full flex-col">
            {loading && (
              <Section
                height="full"
                alignItems="center"
                justifyContent="center"
                padding={8}
              >
                <Text font="secondary-body" color="text-03">
                  {previewT("loading.label")}
                </Text>
              </Section>
            )}
            {!loading && error && (
              <Section
                height="full"
                alignItems="center"
                justifyContent="center"
                padding={8}
              >
                <Text font="heading-h3" color="text-03">
                  {previewT("error.title")}
                </Text>
                <Text font="secondary-body" color="text-02">
                  {error}
                </Text>
              </Section>
            )}
            {!loading && !error && payload?.status === "too-large" && (
              <FallbackNotice
                title={previewT("cannotPreview.title")}
                body={t("detail.preview.tooLarge")}
                href={craftProjectFileUrl(projectId, file.id)}
                downloadLabel={t("detail.download.tooltip")}
              />
            )}
            {!loading &&
              !error &&
              (payload?.status === "unsupported" || kind === "unsupported") && (
                <FallbackNotice
                  title={previewT("cannotPreview.title")}
                  body={t("detail.preview.cannotPreview")}
                  href={craftProjectFileUrl(projectId, file.id)}
                  downloadLabel={t("detail.download.tooltip")}
                />
              )}
            {!loading &&
              !error &&
              payload?.status === "text" &&
              kind === "markdown" && (
                <MarkdownFilePreview
                  content={text}
                  fileName={file.name}
                  filePath={file.path}
                  mimeType={file.mime_type ?? "text/markdown"}
                  isImage={false}
                />
              )}
            {!loading &&
              !error &&
              payload?.status === "text" &&
              (kind === "text" || kind === "json") && (
                <pre className="font-mono text-sm text-text-04 whitespace-pre-wrap wrap-break-word p-4">
                  {text}
                </pre>
              )}
            {!loading && !error && imageUrl && (
              <ImagePreview src={imageUrl} fileName={file.name} />
            )}
            {!loading && !error && payload?.status === "document" && (
              <div className="min-h-0 flex-1">
                <DocumentPreview
                  src={craftProjectFileUrl(projectId, file.id)}
                  fileName={file.name}
                  mimeType={file.mime_type}
                  mode={previewMode}
                  onDirtyChange={setDirty}
                  onSaveBytes={
                    previewMode === "edit"
                      ? async (bytes, mime) => {
                          await saveCraftProjectFileBytes(
                            projectId,
                            file.id,
                            file.name,
                            bytes,
                            mime
                          );
                          await onChanged();
                        }
                      : undefined
                  }
                />
              </div>
            )}
          </div>
        </Modal.Body>
      </Modal.Content>
      <UnsavedChangesModal
        open={confirmClose}
        onCancel={() => setConfirmClose(false)}
        onDiscard={() => {
          setConfirmClose(false);
          setDirty(false);
          onClose();
        }}
      />
    </Modal>
  );
}

function FallbackNotice({
  title,
  body,
  href,
  downloadLabel,
}: {
  title: string;
  body: string;
  href: string;
  downloadLabel: string;
}) {
  return (
    <Section
      height="full"
      alignItems="center"
      justifyContent="center"
      padding={8}
      gap={3}
    >
      <SvgFile size={40} className="stroke-text-02" />
      <Text font="heading-h3" color="text-03">
        {title}
      </Text>
      <Text font="secondary-body" color="text-02">
        {body}
      </Text>
      <Button prominence="secondary" icon={SvgDownload} href={href}>
        {downloadLabel}
      </Button>
    </Section>
  );
}
