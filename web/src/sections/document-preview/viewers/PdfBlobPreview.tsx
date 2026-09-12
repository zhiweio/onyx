"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { Text } from "@opal/components";
import { SvgFileText } from "@opal/icons";
import { Section } from "@/layouts/general-layouts";
import { cn } from "@opal/utils";

interface PdfBlobPreviewProps {
  src: string;
  fileName: string;
}

export default function PdfBlobPreview({ src, fileName }: PdfBlobPreviewProps) {
  const t = useTranslations("craft.documentPreview");
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const blobUrlRef = useRef<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    if (blobUrlRef.current) {
      URL.revokeObjectURL(blobUrlRef.current);
      blobUrlRef.current = null;
    }
    setBlobUrl(null);
    setLoading(true);
    setError(false);

    if (src.startsWith("blob:")) {
      setBlobUrl(src);
      setLoading(false);
      return () => controller.abort();
    }

    fetch(src, { signal: controller.signal })
      .then((res) => {
        if (!res.ok) {
          throw new Error(`Failed to fetch PDF: ${res.status}`);
        }
        return res.blob();
      })
      .then((blob) => {
        const typed =
          blob.type === "application/pdf"
            ? blob
            : new Blob([blob], { type: "application/pdf" });
        const url = URL.createObjectURL(typed);
        blobUrlRef.current = url;
        setBlobUrl(url);
        setLoading(false);
      })
      .catch((err) => {
        if (err instanceof DOMException && err.name === "AbortError") {
          return;
        }
        setError(true);
        setLoading(false);
      });

    return () => {
      controller.abort();
      if (blobUrlRef.current) {
        URL.revokeObjectURL(blobUrlRef.current);
        blobUrlRef.current = null;
      }
    };
  }, [src]);

  if (error) {
    return (
      <Section
        height="full"
        alignItems="center"
        justifyContent="center"
        padding={8}
      >
        <SvgFileText size={48} className="stroke-text-02" />
        <Text font="heading-h3" color="text-03">
          {t("error.title")}
        </Text>
        <Text font="secondary-body" color="text-02">
          {t("error.description")}
        </Text>
      </Section>
    );
  }

  if (loading || !blobUrl) {
    return (
      <Section
        height="full"
        alignItems="center"
        justifyContent="center"
        padding={8}
      >
        <Text font="secondary-body" color="text-03">
          {t("loading.label")}
        </Text>
      </Section>
    );
  }

  return (
    <iframe
      src={blobUrl}
      title={fileName || t("iframeTitle")}
      className={cn("w-full h-full border-none")}
    />
  );
}
