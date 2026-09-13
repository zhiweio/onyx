"use client";

import { useTranslations } from "next-intl";
import type { FileRendererProps } from "@/app/craft/components/output-panel/MarkdownFilePreview";

/** Scripts may run, but the frame stays on a unique origin. */
const HTML_IFRAME_SANDBOX =
  "allow-scripts allow-popups allow-popups-to-escape-sandbox";

export default function HtmlFilePreview({
  content,
  fileName,
}: FileRendererProps) {
  const t = useTranslations("craft.filePreview");

  return (
    <div className="h-full min-h-0">
      <iframe
        title={t("html.frame.title", { fileName })}
        srcDoc={content}
        sandbox={HTML_IFRAME_SANDBOX}
        className="h-full w-full border-0 bg-background-neutral-00"
      />
    </div>
  );
}
