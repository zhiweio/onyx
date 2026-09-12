import { Section } from "@/layouts/general-layouts";
import { DocumentPreview } from "@/sections/document-preview";
import { PreviewVariant } from "@/sections/modals/PreviewModal/interfaces";
import { DownloadButton } from "@/sections/modals/PreviewModal/variants/shared";

export const pptxVariant: PreviewVariant = {
  matches: (name, mime) => {
    const lower = (name || "").toLowerCase();
    return (
      mime.includes("presentationml") ||
      mime === "application/vnd.ms-powerpoint" ||
      (lower.endsWith(".pptx") && !lower.endsWith(".pptx.txt")) ||
      (lower.endsWith(".ppt") && !lower.endsWith(".ppt.txt"))
    );
  },
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
