"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { renderAsync } from "docx-preview";
import { Text } from "@opal/components";
import { Section } from "@/layouts/general-layouts";
import { sanitizeDocxHtml } from "@/sections/modals/PreviewModal/variants/sanitizeDocxHtml";
import "@/sections/modals/PreviewModal/variants/docx-preview.css";
import "@/sections/document-preview/viewers/docx-host.css";

interface DocxHtmlPreviewProps {
  src: string;
  onText?: (plainText: string) => void;
}

export default function DocxHtmlPreview({ src, onText }: DocxHtmlPreviewProps) {
  const t = useTranslations("craft.documentPreview");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const styleRef = useRef<HTMLDivElement>(null);
  const onTextRef = useRef(onText);

  useEffect(() => {
    onTextRef.current = onText;
  }, [onText]);

  useEffect(() => {
    const controller = new AbortController();

    async function loadDocument() {
      setIsLoading(true);
      setError(null);
      try {
        const response = await fetch(src, { signal: controller.signal });
        if (!response.ok) {
          throw new Error(`Failed to fetch document: ${response.status}`);
        }
        const buffer = await response.arrayBuffer();
        if (!bodyRef.current || !styleRef.current) {
          return;
        }
        bodyRef.current.innerHTML = "";
        styleRef.current.innerHTML = "";
        await renderAsync(buffer, bodyRef.current, styleRef.current, {
          className: "docx",
          inWrapper: false,
          ignoreWidth: false,
          ignoreHeight: false,
          ignoreFonts: false,
          breakPages: true,
          useBase64URL: true,
          renderHeaders: true,
          renderFooters: true,
          renderFootnotes: true,
          renderEndnotes: true,
        });
        bodyRef.current.innerHTML = sanitizeDocxHtml(bodyRef.current.innerHTML);
        for (const child of Array.from(styleRef.current.children)) {
          if (child.tagName !== "STYLE") {
            child.remove();
          }
        }
        onTextRef.current?.(bodyRef.current.innerText ?? "");
      } catch (loadError) {
        if (
          loadError instanceof DOMException &&
          loadError.name === "AbortError"
        ) {
          return;
        }
        setError(t("error.description"));
      } finally {
        setIsLoading(false);
      }
    }

    void loadDocument();
    return () => controller.abort();
  }, [src, t]);

  if (error) {
    return (
      <Section
        height="full"
        justifyContent="center"
        alignItems="center"
        padding={6}
      >
        <Text font="secondary-body" color="text-03">
          {error}
        </Text>
      </Section>
    );
  }

  return (
    <div className="h-full overflow-auto bg-background-tint-00">
      {isLoading && (
        <Section padding={6}>
          <Text font="secondary-body" color="text-03">
            {t("loading.label")}
          </Text>
        </Section>
      )}
      <div ref={styleRef} />
      <div ref={bodyRef} className="docx-host px-8 py-8" lang="zh-CN" />
    </div>
  );
}
