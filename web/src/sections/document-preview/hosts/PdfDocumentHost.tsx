"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { PDFEditor } from "@/sections/extend/pdf-editor";
import { PDFViewer } from "@/sections/extend/pdf-viewer";
import type { PDFEditorPageOverlayProps } from "@/sections/extend/pdf-editor";
import type { PDFViewerPageOverlayProps } from "@/sections/extend/pdf-viewer";
import { renderPdfThumbnailUrl } from "@/sections/extend/lib/pdf-thumbnail-utils";
import type { ReviewField } from "@/sections/extend/bounding-box-citations";
import { HumanReviewHighlight } from "@/sections/extend/bounding-box-citations";
import type { ParsedOcrOutput } from "@/sections/extend/layout-blocks";
import { OcrBlockOverlay, getOcrBlocks } from "@/sections/extend/layout-blocks";
import type {
  DocumentSplit,
  DocumentSplitPageId,
} from "@/sections/extend/document-splits";
import {
  DocumentSplits,
  getPageNumber,
  THUMBNAIL_WIDTH,
} from "@/sections/extend/document-splits";

// Thumbnails render in the shared PDFium worker; a small pool keeps the queue
// moving without flooding it on large documents.
const THUMBNAIL_RENDER_CONCURRENCY = 4;

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
  const [thumbnailImages, setThumbnailImages] = useState<
    Record<DocumentSplitPageId, string>
  >({});
  const thumbnailSrcRef = useRef(src);

  // Splits reorder freely, so key the queue on the sorted page set: drag edits
  // keep the same pages and must not restart thumbnail rendering.
  const splitPageNumbersKey = useMemo(() => {
    if (!splits) return "";
    const pages = new Set<number>();
    for (const split of splits) {
      for (const pageId of split.pages) pages.add(getPageNumber(pageId));
    }
    return [...pages].sort((a, b) => a - b).join(",");
  }, [splits]);

  useEffect(() => {
    if (!splitPageNumbersKey) return;
    if (thumbnailSrcRef.current !== src) {
      thumbnailSrcRef.current = src;
      setThumbnailImages({});
    }
    const pageNumbers = splitPageNumbersKey.split(",").map(Number);
    const queue = [...pageNumbers];
    let cancelled = false;
    const loadNext = async () => {
      while (!cancelled && queue.length > 0) {
        const pageNumber = queue.shift();
        if (pageNumber === undefined) break;
        try {
          const imageUrl = await renderPdfThumbnailUrl({
            url: src,
            pageIndex: pageNumber - 1,
            width: THUMBNAIL_WIDTH,
          });
          if (!imageUrl) continue;
          // The thumbnail cache serves the same URLs for the rest of the
          // session, so they are intentionally not revoked.
          const pageId: DocumentSplitPageId = `page-${pageNumber}`;
          setThumbnailImages((prev) => ({ ...prev, [pageId]: imageUrl }));
        } catch {
          // Leave the placeholder box for pages that fail to render.
        }
      }
    };
    void Promise.all(
      Array.from({ length: THUMBNAIL_RENDER_CONCURRENCY }, () => loadNext())
    );
    return () => {
      cancelled = true;
    };
  }, [src, splitPageNumbersKey]);

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
            thumbnailImages={thumbnailImages}
            onSelectPage={() => undefined}
            onSplitsChange={onSplitsChange}
          />
        </div>
      ) : null}
    </div>
  );
}
