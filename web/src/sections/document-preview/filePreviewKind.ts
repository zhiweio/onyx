export type FilePreviewKind =
  | "markdown"
  | "text"
  | "json"
  | "image"
  | "pdf"
  | "docx"
  | "doc"
  | "xlsx"
  | "pptx"
  | "csv"
  | "unsupported";

const IMAGE_EXTENSIONS = new Set([
  "bmp",
  "gif",
  "jpeg",
  "jpg",
  "png",
  "svg",
  "webp",
]);

const TEXT_EXTENSIONS = new Set([
  "css",
  "html",
  "js",
  "jsonl",
  "log",
  "py",
  "sh",
  "ts",
  "tsx",
  "txt",
  "xml",
  "yaml",
  "yml",
]);

export function fileExtension(name: string): string {
  const index = name.lastIndexOf(".");
  if (index <= 0 || index === name.length - 1) {
    return "";
  }
  return name.slice(index + 1).toLowerCase();
}

export function filePreviewKind(
  fileName: string,
  mimeType?: string | null
): FilePreviewKind {
  const ext = fileExtension(fileName);
  const mime = mimeType?.toLowerCase().split(";")[0]?.trim() ?? "";

  if (mime.startsWith("image/") || IMAGE_EXTENSIONS.has(ext)) {
    return "image";
  }
  if (ext === "pdf" || mime === "application/pdf") {
    return "pdf";
  }
  if (ext === "docx" || mime.includes("wordprocessingml.document")) {
    return "docx";
  }
  if (ext === "doc" || mime === "application/msword") {
    return "doc";
  }
  if (
    ext === "xlsx" ||
    ext === "xlsm" ||
    mime.includes("spreadsheetml.sheet")
  ) {
    return "xlsx";
  }
  if (ext === "pptx" || ext === "ppt" || mime.includes("presentationml")) {
    return "pptx";
  }
  if (ext === "csv" || ext === "tsv" || mime === "text/csv") {
    return "csv";
  }
  if (ext === "md" || ext === "markdown") {
    return "markdown";
  }
  if (ext === "json" || (mime.includes("json") && ext !== "jsonl")) {
    return "json";
  }
  if (mime.startsWith("text/") || TEXT_EXTENSIONS.has(ext)) {
    return "text";
  }
  return "unsupported";
}

export function isDocumentPreviewKind(kind: FilePreviewKind): boolean {
  return (
    kind === "pdf" ||
    kind === "docx" ||
    kind === "doc" ||
    kind === "xlsx" ||
    kind === "pptx" ||
    kind === "csv"
  );
}

export function isEditableDocumentKind(kind: FilePreviewKind): boolean {
  return kind === "pdf" || kind === "docx" || kind === "xlsx";
}

export type DocumentPreviewSurface =
  | "craft-project"
  | "chat-project"
  | "sandbox"
  | "chat-preview"
  | "library";

export function resolveDocumentPreviewMode(
  surface: DocumentPreviewSurface,
  kind: FilePreviewKind
): "view" | "edit" {
  const projectSurface =
    surface === "craft-project" || surface === "chat-project";
  return projectSurface && isEditableDocumentKind(kind) ? "edit" : "view";
}

export function isChatProjectFileDocumentId(documentId: string): boolean {
  return documentId.startsWith("project_file__");
}

export function chatFileIdFromDocumentId(documentId: string): string {
  return documentId.split("__")[1] || documentId;
}
