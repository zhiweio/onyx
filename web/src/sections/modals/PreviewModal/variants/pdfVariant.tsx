import { Section } from "@/layouts/general-layouts";
import { DocumentPreview } from "@/sections/document-preview";
import { PreviewVariant } from "@/sections/modals/PreviewModal/interfaces";
import { DownloadButton } from "@/sections/modals/PreviewModal/variants/shared";

export const pdfVariant: PreviewVariant = {
  matches: (_name, mime) => mime === "application/pdf",
  width: "full",
  height: "full",
  needsTextContent: false,
  codeBackground: false,
  headerDescription: () => "",

  renderContent: (ctx) => (
    <DocumentPreview src={ctx.fileUrl} fileName={ctx.fileName} mode="view" />
  ),

  renderFooterLeft: () => null,
  renderFooterRight: (ctx) => (
    <Section flexDirection="row" width="fit">
      <DownloadButton fileUrl={ctx.fileUrl} fileName={ctx.fileName} />
    </Section>
  ),
};
