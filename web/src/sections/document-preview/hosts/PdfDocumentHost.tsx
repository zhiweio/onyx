"use client";

import { useRef } from "react";
import { PDFEditor } from "@/sections/extend/pdf-editor";
import { PDFViewer } from "@/sections/extend/pdf-viewer";
import type { PDFEditorPageOverlayProps } from "@/sections/extend/pdf-editor";
import type { PDFViewerPageOverlayProps } from "@/sections/extend/pdf-viewer";
import type { ReviewField } from "@/sections/extend/bounding-box-citations";
import { HumanReviewHighlight } from "@/sections/extend/bounding-box-citations";
import type { ParsedOcrOutput } from "@/sections/extend/layout-blocks";
import { OcrBlockOverlay, getOcrBlocks } from "@/sections/extend/layout-blocks";
import type { DocumentSplit } from "@/sections/extend/document-splits";
import { DocumentSplits } from "@/sections/extend/document-splits";

export interface PdfDocumentHostProps {
  src: string;
  fileName: string;
  mode: "view" | "edit";
  showDownload: boolean;
  toolbarActions?: React.ReactNode;
  reviewFields?: ReviewField[];
  ocrOutput?: ParsedOcrOutput;
  splits?: DocumentSplit[];
  onSplitsChange?: (splits: DocumentSplit[]) => void;
  onPageCount?: (count: number) => void;
  onDirty?: () => void;
  onSave?: (result: { buffer: ArrayBuffer; fileName: string }) => void;
}

export default function PdfDocumentHost({
  src,
  fileName,
  mode,
  showDownload,
  toolbarActions,
  reviewFields,
  ocrOutput,
  splits,
  onSplitsChange,
  onPageCount,
  onDirty,
  onSave,
}: PdfDocumentHostProps) {
  const pageRef = useRef(1);

  const overlay = (
    props: PDFEditorPageOverlayProps | PDFViewerPageOverlayProps
  ) => {
    const reviewLocations = (reviewFields ?? [])
      .map((field) => field.location)
      .filter(
        (location): location is NonNullable<typeof location> =>
          location != null && location.page === props.pageNumber
      );
    const ocrBlocks = ocrOutput
      ? getOcrBlocks(ocrOutput).filter(
          (block) => block.page === props.pageNumber
        )
      : [];
    return (
      <>
        {reviewLocations.map((location, index) => (
          <HumanReviewHighlight
            key={`${location.page}-${location.area.left}-${index}`}
            location={location}
          />
        ))}
        {ocrBlocks.map((block) => (
          <OcrBlockOverlay
            key={block.id}
            block={block}
            pageWidth={props.pageWidth}
            pageHeight={props.pageHeight}
          />
        ))}
      </>
    );
  };

  return (
    <div className="flex h-full min-h-0 w-full">
      <div className="min-h-0 min-w-0 flex-1">
        {mode === "edit" ? (
          <PDFEditor
            src={src}
            fileName={fileName}
            showUpload={false}
            showDownload={showDownload}
            toolbarActions={toolbarActions}
            renderPageOverlay={overlay}
            onDocumentLoadSuccess={(info) => onPageCount?.(info.numPages)}
            onAnnotationsChange={() => onDirty?.()}
            onFormValuesChange={() => onDirty?.()}
            onSave={onSave}
          />
        ) : (
          <PDFViewer
            src={src}
            fileName={fileName}
            showUpload={false}
            showDownload={showDownload}
            toolbarActions={toolbarActions}
            renderPageOverlay={overlay}
            onDocumentLoadSuccess={(count) => onPageCount?.(count)}
            onActivePageChange={(page) => {
              pageRef.current = page;
            }}
          />
        )}
      </div>
      {splits && onSplitsChange ? (
        <div className="w-64 shrink-0 overflow-auto border-s border-border-01">
          <DocumentSplits
            splits={splits}
            onSelectPage={() => undefined}
            onSplitsChange={onSplitsChange}
          />
        </div>
      ) : null}
    </div>
  );
}
