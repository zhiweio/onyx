export function isHtmlFilePath(filePath: string): boolean {
  return /\.html?$/i.test(filePath);
}

export function htmlDownloadExtension(filePath: string): ".html" | ".htm" {
  return filePath.toLowerCase().endsWith(".htm") ? ".htm" : ".html";
}
