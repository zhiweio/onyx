"use client";

import { CsvViewer } from "@/sections/extend/csv-viewer";
import { DocxEditorPreview } from "@/sections/extend/docx-editor";
import { DocxViewerPreview } from "@/sections/extend/docx-viewer";
import { PptxViewerPreview } from "@/sections/extend/pptx-viewer";
import { XlsxEditorPreview } from "@/sections/extend/xlsx-editor";
import { XlsxViewerPreview } from "@/sections/extend/xlsx-viewer";
import { useExtendTheme } from "@/sections/document-preview/hosts/ExtendTheme";
import { useEffect, useState } from "react";

export function DocxDocumentHost({
  src,
  fileName,
  mode,
  toolbarActions,
  onDirty,
}: {
  src: string;
  fileName: string;
  mode: "view" | "edit";
  toolbarActions?: React.ReactNode;
  onDirty?: () => void;
}) {
  const theme = useExtendTheme();
  if (mode === "edit") {
    return (
      <div className="flex h-full min-h-0 flex-col">
        {toolbarActions}
        <form
          className="min-h-0 flex-1"
          onInput={onDirty}
          onSubmit={(event) => event.preventDefault()}
        >
          <DocxEditorPreview
            className="h-full"
            src={src}
            fileName={fileName}
            isDark={theme.isDark}
            onIsDarkChange={theme.onIsDarkChange}
          />
        </form>
      </div>
    );
  }
  return (
    <div className="flex h-full min-h-0 flex-col">
      <DocxViewerPreview
        className="h-full min-h-0"
        src={src}
        fileName={fileName}
        isDark={false}
        onIsDarkChange={() => undefined}
        showNightRenderToggle={false}
        showUpload={false}
        toolbarActions={toolbarActions}
      />
    </div>
  );
}

export function XlsxDocumentHost({
  src,
  fileName,
  mode,
  toolbarActions,
  onDirty,
}: {
  src: string;
  fileName: string;
  mode: "view" | "edit";
  toolbarActions?: React.ReactNode;
  onDirty?: () => void;
}) {
  const theme = useExtendTheme();
  if (mode === "edit") {
    return (
      <div className="flex h-full min-h-0 flex-col">
        {toolbarActions}
        <form
          className="min-h-0 flex-1"
          onInput={onDirty}
          onSubmit={(event) => event.preventDefault()}
        >
          <XlsxEditorPreview
            src={src}
            fileName={fileName}
            isDark={theme.isDark}
            onIsDarkChange={theme.onIsDarkChange}
          />
        </form>
      </div>
    );
  }
  return (
    <XlsxViewerPreview
      src={src}
      fileName={fileName}
      isDark={theme.isDark}
      onIsDarkChange={theme.onIsDarkChange}
      showUpload={false}
    />
  );
}

export function PptxDocumentHost({
  src,
  fileName,
}: {
  src: string;
  fileName: string;
}) {
  return <PptxViewerPreview src={src} fileName={fileName} showUpload={false} />;
}

export function CsvDocumentHost({ src }: { src: string }) {
  const [data, setData] = useState<string>("");
  useEffect(() => {
    const controller = new AbortController();
    void fetch(src, { signal: controller.signal })
      .then((response) => response.text())
      .then((text) => setData(text))
      .catch(() => setData(""));
    return () => controller.abort();
  }, [src]);
  return <CsvViewer data={data} search />;
}
