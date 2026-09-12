const PDF_MAGIC = [0x25, 0x50, 0x44, 0x46]; // %PDF
const ZIP_MAGIC = [0x50, 0x4b]; // PK

const BINARY_EXTENSIONS = new Set([
  "doc",
  "docx",
  "pdf",
  "ppt",
  "pptx",
  "xls",
  "xlsx",
  "xlsm",
]);

function fileExtension(path: string): string {
  const slash = Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\"));
  const name = slash >= 0 ? path.slice(slash + 1) : path;
  const dot = name.lastIndexOf(".");
  if (dot <= 0 || dot === name.length - 1) {
    return "";
  }
  return name.slice(dot + 1).toLowerCase();
}

function startsWith(bytes: Uint8Array, magic: number[]): boolean {
  if (bytes.length < magic.length) {
    return false;
  }
  return magic.every((value, index) => bytes[index] === value);
}

export function isBinaryDocument(
  bytes: Uint8Array,
  path: string,
  mimeType?: string | null
): boolean {
  if (startsWith(bytes, PDF_MAGIC) || startsWith(bytes, ZIP_MAGIC)) {
    return true;
  }
  const ext = fileExtension(path);
  if (BINARY_EXTENSIONS.has(ext)) {
    return true;
  }
  const mime = mimeType?.toLowerCase().split(";")[0]?.trim() ?? "";
  return (
    mime === "application/pdf" ||
    mime.includes("officedocument") ||
    mime === "application/msword" ||
    mime === "application/vnd.ms-excel" ||
    mime === "application/vnd.ms-powerpoint"
  );
}

export const BINARY_DOCUMENT_TEXT_ERROR =
  "This file is a binary document and cannot be shown as text.";
