"use client";

import { Section } from "@/layouts/general-layouts";
import { DocumentPreview } from "@/sections/document-preview";
import { PreviewContext } from "@/sections/modals/PreviewModal/interfaces";
import { PreviewVariant } from "@/sections/modals/PreviewModal/interfaces";
import { DownloadButton } from "@/sections/modals/PreviewModal/variants/shared";

const DOCX_MIMES = [
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/msword",
];

function isLegacyDoc(fileName: string): boolean {
  const lower = fileName.toLowerCase();
  return lower.endsWith(".doc") && !lower.endsWith(".docx");
}

export const docxVariant: PreviewVariant = {
  matches: (name, mime) => {
    if (DOCX_MIMES.some((m) => mime === m)) return true;
    const lower = (name || "").toLowerCase();
    return lower.endsWith(".docx") || lower.endsWith(".doc");
  },
  width: "full",
  height: "full",
  needsTextContent: false,
  codeBackground: false,
  headerDescription: (ctx: PreviewContext) =>
    ctx.t("docx.headerDescriptionFallback"),

  renderContent: (ctx: PreviewContext) => {
    if (isLegacyDoc(ctx.fileName)) {
      return (
        <DocumentPreview
          src={ctx.fileUrl}
          fileName={ctx.fileName}
          mimeType="application/msword"
          mode="view"
        />
      );
    }
    return (
      <DocumentPreview src={ctx.fileUrl} fileName={ctx.fileName} mode="view" />
    );
  },

  renderFooterLeft: () => null,
  renderFooterRight: (ctx: PreviewContext) => (
    <Section flexDirection="row" width="fit">
      <DownloadButton fileUrl={ctx.fileUrl} fileName={ctx.fileName} />
    </Section>
  ),
};
