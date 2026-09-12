"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Text } from "@opal/components";
import { Section } from "@/layouts/general-layouts";
import {
  parseSpreadsheetPreview,
  SpreadsheetSheetsView,
  type SpreadsheetSheet,
} from "@/components/tools/SpreadsheetContent";

interface SpreadsheetUrlPreviewProps {
  src: string;
}

function withParsedQuery(src: string): string {
  if (src.startsWith("blob:")) {
    return src;
  }
  try {
    const url = new URL(src, window.location.origin);
    url.searchParams.set("parsed", "true");
    return `${url.pathname}${url.search}`;
  } catch {
    const join = src.includes("?") ? "&" : "?";
    return `${src}${join}parsed=true`;
  }
}

export default function SpreadsheetUrlPreview({
  src,
}: SpreadsheetUrlPreviewProps) {
  const t = useTranslations("craft.documentPreview");
  const [sheets, setSheets] = useState<SpreadsheetSheet[] | null>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(false);
    setSheets(null);

    async function load() {
      try {
        const response = await fetch(withParsedQuery(src), {
          signal: controller.signal,
        });
        if (!response.ok) {
          throw new Error(`Failed to fetch spreadsheet: ${response.status}`);
        }
        const preview = parseSpreadsheetPreview(await response.text());
        if (!preview || preview.sheets.length === 0) {
          throw new Error("Failed to parse spreadsheet preview");
        }
        setSheets(preview.sheets);
      } catch (loadError) {
        if (
          loadError instanceof DOMException &&
          loadError.name === "AbortError"
        ) {
          return;
        }
        setError(true);
      } finally {
        setLoading(false);
      }
    }

    void load();
    return () => controller.abort();
  }, [src]);

  if (loading) {
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

  if (error || !sheets) {
    return (
      <Section
        height="full"
        alignItems="center"
        justifyContent="center"
        padding={8}
      >
        <Text font="heading-h3" color="text-03">
          {t("error.title")}
        </Text>
        <Text font="secondary-body" color="text-02">
          {t("error.description")}
        </Text>
      </Section>
    );
  }

  return (
    <SpreadsheetSheetsView sheets={sheets} className="flex-1 min-h-0 p-1" />
  );
}
