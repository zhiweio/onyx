"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { useTranslations } from "next-intl";
import { MinimalOnyxDocument } from "@/lib/search/interfaces";
import { Modal } from "@opal/components";
import Text from "@/refresh-components/texts/Text";
import { Button } from "@opal/components";
import { SvgSimpleLoader } from "@opal/icons";
import { Section } from "@/layouts/general-layouts";
import FloatingFooter from "@/sections/modals/PreviewModal/FloatingFooter";
import mime from "mime";
import {
  getCodeLanguage,
  getDataLanguage,
  getLanguageByMime,
} from "@/lib/languages";
import { fetchChatFile } from "@/lib/chat/svc";
import { PreviewContext } from "@/sections/modals/PreviewModal/interfaces";
import { resolveVariant } from "@/sections/modals/PreviewModal/variants";
import {
  DocumentPreview,
  saveChatProjectFileBytes,
} from "@/sections/document-preview";
import {
  chatFileIdFromDocumentId,
  filePreviewKind,
  isChatProjectFileDocumentId,
  isDocumentPreviewKind,
  resolveDocumentPreviewMode,
} from "@/sections/document-preview/filePreviewKind";
import UnsavedChangesModal from "@/sections/modals/UnsavedChangesModal";

interface PreviewModalProps {
  presentingDocument: MinimalOnyxDocument;
  onClose: () => void;
}

export default function PreviewModal({
  presentingDocument,
  onClose,
}: PreviewModalProps) {
  const t = useTranslations("chat.modals.preview");
  const [fileContent, setFileContent] = useState("");
  const [fileUrl, setFileUrl] = useState("");
  const [fileName, setFileName] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [mimeType, setMimeType] = useState("application/octet-stream");
  const [zoom, setZoom] = useState(100);
  const [dirty, setDirty] = useState(false);
  const [confirmClose, setConfirmClose] = useState(false);

  const variant = useMemo(
    () => resolveVariant(presentingDocument.semantic_identifier, mimeType),
    [presentingDocument.semantic_identifier, mimeType]
  );

  const language = useMemo(
    () =>
      getCodeLanguage(presentingDocument.semantic_identifier || "") ||
      getLanguageByMime(mimeType) ||
      getDataLanguage(presentingDocument.semantic_identifier || "") ||
      "plaintext",
    [mimeType, presentingDocument.semantic_identifier]
  );

  const lineCount = useMemo(() => {
    if (!fileContent) return 0;
    return fileContent.split("\n").length;
  }, [fileContent]);

  const fileSize = useMemo(() => {
    if (!fileContent) return "";
    const bytes = new TextEncoder().encode(fileContent).length;
    if (bytes < 1024) return `${bytes} B`;
    const kb = bytes / 1024;
    if (kb < 1024) return `${kb.toFixed(2)} KB`;
    const mb = kb / 1024;
    return `${mb.toFixed(2)} MB`;
  }, [fileContent]);

  const fetchFile = useCallback(async () => {
    setIsLoading(true);
    setLoadError(null);
    setFileContent("");
    const fileIdLocal =
      presentingDocument.document_id.split("__")[1] ||
      presentingDocument.document_id;
    const originalFileName =
      presentingDocument.semantic_identifier || "document";
    // Direct raw-file URL — usable for downloads without materializing a blob.
    const rawFileUrl = `/api/chat/file/${encodeURIComponent(fileIdLocal)}`;

    const updateFileUrl = (url: string) =>
      setFileUrl((prev) => {
        if (prev.startsWith("blob:")) window.URL.revokeObjectURL(prev);
        return url;
      });

    try {
      setFileName(originalFileName);

      const guessedMime =
        mime.getType(originalFileName) ?? "application/octet-stream";
      const documentKind = filePreviewKind(originalFileName, guessedMime);
      if (isDocumentPreviewKind(documentKind)) {
        updateFileUrl(rawFileUrl);
        setMimeType(guessedMime);
        return;
      }

      // Variants that render from backend-parsed content (spreadsheets) don't
      // need the raw binary blob — skip downloading the full workbook and let
      // the download button point at the raw URL directly.
      const preResolved = resolveVariant(
        presentingDocument.semantic_identifier,
        "application/octet-stream"
      );
      if (preResolved.needsParsedContent) {
        updateFileUrl(rawFileUrl);
        setMimeType(
          mime.getType(originalFileName) ?? "application/octet-stream"
        );
        const parsedResponse = await fetchChatFile(fileIdLocal, true);
        setFileContent(await parsedResponse.text());
        return;
      }

      const response = await fetchChatFile(fileIdLocal);

      // Re-resolve using the stored MIME from the response headers, which is
      // authoritative, BEFORE materializing the body as a blob.
      const rawContentType =
        response.headers.get("Content-Type") || "application/octet-stream";
      const resolvedMime =
        rawContentType === "application/octet-stream"
          ? (mime.getType(originalFileName) ?? rawContentType)
          : rawContentType;
      setMimeType(resolvedMime);

      const resolved = resolveVariant(
        presentingDocument.semantic_identifier,
        resolvedMime
      );
      if (resolved.needsParsedContent) {
        // Name alone didn't identify a spreadsheet, but the stored MIME did
        // (e.g. an xlsx with a renamed/missing display name). Discard the raw
        // workbook body and render from the parsed payload instead.
        await response.body?.cancel();
        updateFileUrl(rawFileUrl);
        const parsedResponse = await fetchChatFile(fileIdLocal, true);
        setFileContent(await parsedResponse.text());
        return;
      }

      const blob = await response.blob();
      updateFileUrl(window.URL.createObjectURL(blob));

      if (resolved.needsTextContent) {
        setFileContent(await blob.text());
      }
    } catch (error) {
      console.error(
        `Failed to load preview for chat file ${fileIdLocal}:`,
        error
      );
      // Keep a usable download link for the CURRENT file even when the
      // preview itself failed (a stale previous-file URL must never win).
      updateFileUrl(rawFileUrl);
      setLoadError(t("loadError.message"));
    } finally {
      setIsLoading(false);
    }
  }, [presentingDocument, t]);

  useEffect(() => {
    setDirty(false);
    setConfirmClose(false);
    fetchFile();
  }, [fetchFile]);

  useEffect(() => {
    return () => {
      if (fileUrl.startsWith("blob:")) window.URL.revokeObjectURL(fileUrl);
    };
  }, [fileUrl]);

  const handleZoomIn = useCallback(
    () => setZoom((prev) => Math.min(prev + 25, 200)),
    []
  );
  const handleZoomOut = useCallback(
    () => setZoom((prev) => Math.max(prev - 25, 25)),
    []
  );

  const previewKind = filePreviewKind(fileName, mimeType);
  const previewMode = resolveDocumentPreviewMode(
    isChatProjectFileDocumentId(presentingDocument.document_id)
      ? "chat-project"
      : "chat-preview",
    previewKind
  );

  const requestClose = useCallback(() => {
    if (dirty) {
      setConfirmClose(true);
      return;
    }
    onClose();
  }, [dirty, onClose]);

  const ctx: PreviewContext = useMemo(
    () => ({
      fileContent,
      fileUrl,
      fileName,
      language,
      lineCount,
      fileSize,
      zoom,
      onZoomIn: handleZoomIn,
      onZoomOut: handleZoomOut,
      t,
    }),
    [
      fileContent,
      fileUrl,
      fileName,
      language,
      lineCount,
      fileSize,
      zoom,
      handleZoomIn,
      handleZoomOut,
      t,
    ]
  );

  return (
    <Modal
      open
      onOpenChange={(open) => {
        if (!open) requestClose();
      }}
    >
      <Modal.Content
        width={variant.width}
        height={variant.height}
        preventAccidentalClose={false}
        onOpenAutoFocus={(e) => e.preventDefault()}
      >
        <Modal.Header
          title={fileName || t("header.fallbackTitle")}
          description={variant.headerDescription(ctx)}
          onClose={requestClose}
        />

        {/* Body — uses flex-1/min-h-0/overflow-hidden (not Modal.Body)
            so that child ScrollIndicatorDivs become the actual scroll
            container instead of the body stealing it via overflow-y-auto. */}
        <div className="flex flex-col flex-1 min-h-0 overflow-hidden w-full bg-background-tint-01">
          {isLoading ? (
            <Section>
              <SvgSimpleLoader className="h-8 w-8" />
            </Section>
          ) : loadError ? (
            <Section padding={4}>
              <Text text03 mainUiBody>
                {loadError}
              </Text>
              {fileUrl && (
                <a href={fileUrl} download={fileName}>
                  <Button>{t("downloadButton.label")}</Button>
                </a>
              )}
            </Section>
          ) : isDocumentPreviewKind(previewKind) ? (
            <DocumentPreview
              src={fileUrl}
              fileName={fileName}
              mimeType={mimeType}
              mode={previewMode}
              onDirtyChange={setDirty}
              onSaveBytes={
                previewMode === "edit"
                  ? async (bytes, mime) => {
                      await saveChatProjectFileBytes(
                        chatFileIdFromDocumentId(
                          presentingDocument.document_id
                        ),
                        fileName,
                        bytes,
                        mime
                      );
                    }
                  : undefined
              }
            />
          ) : (
            variant.renderContent(ctx)
          )}
        </div>

        {!isLoading && !loadError && (
          <FloatingFooter
            left={variant.renderFooterLeft(ctx)}
            right={variant.renderFooterRight(ctx)}
            codeBackground={variant.codeBackground}
          />
        )}
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
