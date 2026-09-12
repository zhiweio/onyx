"use client";

import { useMemo, type ReactNode } from "react";
import MinimalMarkdown from "@/components/chat/MinimalMarkdown";
import { makeMarkdownPreviewUrlTransform } from "@/app/craft/utils/markdownImages";

/** Shared interface for the file renderer registry */
export interface FileRendererProps {
  content: string;
  fileName: string;
  filePath: string;
  mimeType: string;
  isImage: boolean;
  sessionId?: string;
}

export default function MarkdownFilePreview({
  content,
  filePath,
  sessionId,
}: FileRendererProps) {
  const urlTransform = useMemo(
    () => makeMarkdownPreviewUrlTransform(sessionId, filePath),
    [sessionId, filePath]
  );

  return (
    <div className="h-full min-h-0 overflow-auto p-6">
      <MinimalMarkdown
        content={content}
        className="max-w-3xl mx-auto prose-headings:leading-snug"
        urlTransform={urlTransform}
        components={{
          a: ({ href, children }: { href?: string; children?: ReactNode }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-link hover:text-link-hover underline"
            >
              {children}
            </a>
          ),
          img: ({ src, alt }: { src?: string; alt?: string }) => (
            <img
              src={src}
              alt={alt ?? ""}
              className="max-w-full h-auto rounded-08"
            />
          ),
        }}
      />
    </div>
  );
}
