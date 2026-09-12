import { Section } from "@/layouts/general-layouts";
import { DocumentPreview } from "@/sections/document-preview";
import { PreviewVariant } from "@/sections/modals/PreviewModal/interfaces";
import { DownloadButton } from "@/sections/modals/PreviewModal/variants/shared";
import { isSpreadsheetFileName } from "@/components/tools/SpreadsheetContent";

const SPREADSHEET_MIME_TYPES = [
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "application/vnd.ms-excel.sheet.macroenabled.12",
];

function isSpreadsheetMimeType(mime: string): boolean {
  const normalized = mime.split(";")[0]?.trim().toLowerCase() ?? "";
  return SPREADSHEET_MIME_TYPES.includes(normalized);
}

export const xlsxVariant: PreviewVariant = {
  matches: (name, mime) =>
    isSpreadsheetMimeType(mime) || isSpreadsheetFileName(name),
  width: "full",
  height: "full",
  needsTextContent: false,
  needsParsedContent: false,
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
