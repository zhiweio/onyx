import {
  packageToArrayBuffer,
  parseDocx,
  withPart,
} from "@extend-ai/react-docx";
import {
  isRewritableDocxPartName,
  rewriteDocxXmlForReadableLineSpacing,
} from "@/sections/document-preview/readableDocxSpacing";

const DOCX_MIME_TYPE =
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

export async function fileWithReadableDocxLineSpacing(
  file: File
): Promise<File> {
  try {
    let pkg = await parseDocx(await file.arrayBuffer());
    let changed = false;
    for (const [name, part] of pkg.parts) {
      if (!isRewritableDocxPartName(name)) {
        continue;
      }
      const rewritten = rewriteDocxXmlForReadableLineSpacing(part.content);
      if (rewritten === part.content) {
        continue;
      }
      pkg = withPart(pkg, { name, content: rewritten });
      changed = true;
    }
    if (!changed) {
      return file;
    }
    const buffer = await packageToArrayBuffer(pkg);
    return new File([buffer], file.name, {
      type: file.type || DOCX_MIME_TYPE,
    });
  } catch {
    return file;
  }
}
