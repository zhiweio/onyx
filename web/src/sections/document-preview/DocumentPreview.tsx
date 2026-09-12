"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { useTranslations } from "next-intl";
import { Button, Text } from "@opal/components";
import { toast } from "@opal/layouts";
import { Section } from "@/layouts/general-layouts";
import {
  filePreviewKind,
  isEditableDocumentKind,
  type FilePreviewKind,
} from "@/sections/document-preview/filePreviewKind";
import { captureObjectUrlExport } from "@/sections/document-preview/captureExport";
import type { ReviewField } from "@/sections/extend/bounding-box-citations";
import type { ParsedOcrOutput } from "@/sections/extend/layout-blocks";
import {
  createInitialSplits,
  type DocumentSplit,
} from "@/sections/extend/document-splits";

const PdfDocumentHost = dynamic(
  () => import("@/sections/document-preview/hosts/PdfDocumentHost"),
  { ssr: false }
);
const DocxDocumentHost = dynamic(
  () =>
    import("@/sections/document-preview/hosts/OfficeDocumentHost").then(
      (mod) => mod.DocxDocumentHost
    ),
  { ssr: false }
);
const XlsxDocumentHost = dynamic(
  () =>
    import("@/sections/document-preview/hosts/OfficeDocumentHost").then(
      (mod) => mod.XlsxDocumentHost
    ),
  { ssr: false }
);
const PptxDocumentHost = dynamic(
  () =>
    import("@/sections/document-preview/hosts/OfficeDocumentHost").then(
      (mod) => mod.PptxDocumentHost
    ),
  { ssr: false }
);
const CsvDocumentHost = dynamic(
  () =>
    import("@/sections/document-preview/hosts/OfficeDocumentHost").then(
      (mod) => mod.CsvDocumentHost
    ),
  { ssr: false }
);

export type DocumentPreviewMode = "view" | "edit";
export type DocumentPreviewLayout = "panel" | "modal" | "inline";

export interface DocumentPreviewProps {
  src: string;
  fileName: string;
  mimeType?: string | null;
  layout?: DocumentPreviewLayout;
  mode?: DocumentPreviewMode;
  onSaveBytes?: (bytes: Uint8Array, mimeType: string) => Promise<void>;
  showUpload?: boolean;
  showDownload?: boolean;
  reviewFields?: ReviewField[];
  ocrOutput?: ParsedOcrOutput;
  onDirtyChange?: (dirty: boolean) => void;
}

const PDF_MIME = "application/pdf";
const DOCX_MIME =
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
const XLSX_MIME =
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
const LARGE_PDF_PAGE_COUNT = 8;

function mimeForKind(kind: FilePreviewKind): string {
  if (kind === "pdf") return PDF_MIME;
  if (kind === "docx") return DOCX_MIME;
  if (kind === "xlsx") return XLSX_MIME;
  return "application/octet-stream";
}

export default function DocumentPreview({
  src,
  fileName,
  mimeType,
  mode = "view",
  onSaveBytes,
  showDownload = true,
  reviewFields,
  ocrOutput,
  onDirtyChange,
}: DocumentPreviewProps) {
  const t = useTranslations("craft.documentPreview");
  const kind = useMemo(
    () => filePreviewKind(fileName, mimeType),
    [fileName, mimeType]
  );
  const canEdit =
    mode === "edit" && isEditableDocumentKind(kind) && Boolean(onSaveBytes);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [pageCount, setPageCount] = useState(0);
  const [splits, setSplits] = useState<DocumentSplit[] | null>(null);

  const markDirty = useCallback(() => setDirty(true), []);

  useEffect(() => {
    onDirtyChange?.(dirty);
  }, [dirty, onDirtyChange]);

  const handleOfficeSave = useCallback(async () => {
    if (!onSaveBytes) return;
    setSaving(true);
    try {
      const bytes = await captureObjectUrlExport(() => {
        if (kind === "docx") {
          document
            .querySelector<HTMLButtonElement>('[aria-label="Download DOCX"]')
            ?.click();
          return;
        }
        document
          .querySelector<HTMLElement>("[aria-label='Export XLSX']")
          ?.click();
      });
      await onSaveBytes(bytes, mimeForKind(kind));
      setDirty(false);
      toast.success(t("saved.message"));
    } catch {
      toast.error(t("saveFailed.message"));
    } finally {
      setSaving(false);
    }
  }, [kind, onSaveBytes, t]);

  const saveToolbar =
    canEdit && kind !== "pdf" ? (
      <div className="flex items-center justify-end gap-2 border-b border-border-01 px-3 py-2">
        <Button
          prominence="primary"
          size="sm"
          disabled={saving}
          onClick={() => {
            void handleOfficeSave();
          }}
        >
          {saving ? t("saving.label") : t("save.label")}
        </Button>
      </div>
    ) : null;

  const pdfSplits =
    kind === "pdf" && mode === "view" && pageCount >= LARGE_PDF_PAGE_COUNT
      ? (splits ?? createInitialSplits(pageCount))
      : undefined;

  if (kind === "pdf") {
    return (
      <div className="flex h-full min-h-0 w-full flex-col">
        <div className="min-h-0 flex-1">
          <PdfDocumentHost
            src={src}
            fileName={fileName}
            mode={canEdit ? "edit" : "view"}
            showDownload={showDownload}
            reviewFields={reviewFields}
            ocrOutput={ocrOutput}
            splits={pdfSplits}
            onSplitsChange={pdfSplits ? (next) => setSplits(next) : undefined}
            onPageCount={setPageCount}
            onDirty={markDirty}
            onSave={
              canEdit && onSaveBytes
                ? async ({ buffer }) => {
                    try {
                      await onSaveBytes(new Uint8Array(buffer), PDF_MIME);
                      setDirty(false);
                      toast.success(t("saved.message"));
                    } catch {
                      toast.error(t("saveFailed.message"));
                    }
                  }
                : undefined
            }
          />
        </div>
        {dirty && canEdit ? (
          <Text font="secondary-body" color="text-03">
            {t("dirty.message")}
          </Text>
        ) : null}
      </div>
    );
  }

  if (kind === "docx") {
    return (
      <div className="flex h-full min-h-0 w-full flex-col">
        <DocxDocumentHost
          src={src}
          fileName={fileName}
          mode={canEdit ? "edit" : "view"}
          toolbarActions={saveToolbar}
          onDirty={canEdit ? markDirty : undefined}
        />
        {dirty && canEdit ? (
          <Text font="secondary-body" color="text-03">
            {t("dirty.message")}
          </Text>
        ) : null}
      </div>
    );
  }
  if (kind === "xlsx") {
    return (
      <div className="flex h-full min-h-0 w-full flex-col">
        <XlsxDocumentHost
          src={src}
          fileName={fileName}
          mode={canEdit ? "edit" : "view"}
          toolbarActions={saveToolbar}
          onDirty={canEdit ? markDirty : undefined}
        />
        {dirty && canEdit ? (
          <Text font="secondary-body" color="text-03">
            {t("dirty.message")}
          </Text>
        ) : null}
      </div>
    );
  }
  if (kind === "pptx") {
    return <PptxDocumentHost src={src} fileName={fileName} />;
  }
  if (kind === "csv") {
    return <CsvDocumentHost src={src} />;
  }
  if (kind === "doc") {
    return (
      <Section
        height="full"
        alignItems="center"
        justifyContent="center"
        padding={8}
      >
        <Text font="secondary-body" color="text-02">
          {t("legacyDoc.message")}
        </Text>
      </Section>
    );
  }
  return (
    <Section
      height="full"
      alignItems="center"
      justifyContent="center"
      padding={8}
    >
      <Text font="secondary-body" color="text-02">
        {t("unsupported.message")}
      </Text>
    </Section>
  );
}
