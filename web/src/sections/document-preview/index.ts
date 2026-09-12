export { default as DocumentPreview } from "@/sections/document-preview/DocumentPreview";
export type {
  DocumentPreviewMode,
  DocumentPreviewProps,
} from "@/sections/document-preview/DocumentPreview";
export {
  filePreviewKind,
  isChatProjectFileDocumentId,
  isDocumentPreviewKind,
  isEditableDocumentKind,
  resolveDocumentPreviewMode,
} from "@/sections/document-preview/filePreviewKind";
export type {
  DocumentPreviewSurface,
  FilePreviewKind,
} from "@/sections/document-preview/filePreviewKind";
export {
  craftFilesToItems,
  flattenLibraryTree,
  flattenSandboxCache,
  fileSystemFileId,
} from "@/sections/document-preview/FileSystemAdapter";
export {
  isBinaryDocument,
  BINARY_DOCUMENT_TEXT_ERROR,
} from "@/sections/document-preview/binaryGuard";
export {
  saveCraftProjectFileBytes,
  saveChatProjectFileBytes,
} from "@/sections/document-preview/saveProjectFile";
