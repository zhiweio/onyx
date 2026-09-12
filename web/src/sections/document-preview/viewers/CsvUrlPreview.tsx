"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Text } from "@opal/components";
import { Section } from "@/layouts/general-layouts";

interface CsvUrlPreviewProps {
  src: string;
}

function parseCsv(content: string): { headers: string[]; rows: string[][] } {
  const lines = content.split(/\r?\n/).filter((line) => line.length > 0);
  const headers = lines.length > 0 ? (lines[0]?.split(",") ?? []) : [];
  const rows = lines.slice(1).map((line) => line.split(","));
  return { headers, rows };
}

export default function CsvUrlPreview({ src }: CsvUrlPreviewProps) {
  const t = useTranslations("craft.documentPreview");
  const [content, setContent] = useState<string | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    setContent(null);
    setError(false);
    fetch(src, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Failed to fetch CSV: ${response.status}`);
        }
        return response.text();
      })
      .then((text) => setContent(text))
      .catch((loadError) => {
        if (
          loadError instanceof DOMException &&
          loadError.name === "AbortError"
        ) {
          return;
        }
        setError(true);
      });
    return () => controller.abort();
  }, [src]);

  if (error) {
    return (
      <Section
        height="full"
        alignItems="center"
        justifyContent="center"
        padding={8}
      >
        <Text font="secondary-body" color="text-03">
          {t("error.description")}
        </Text>
      </Section>
    );
  }

  if (content === null) {
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

  const { headers, rows } = parseCsv(content);
  return (
    <Section justifyContent="start" alignItems="start" padding={4}>
      <Table>
        <TableHeader>
          <TableRow>
            {headers.map((header, index) => (
              <TableHead key={`${header}-${index}`}>{header}</TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row, rowIndex) => (
            <TableRow key={rowIndex}>
              {row.map((cell, cellIndex) => (
                <TableCell key={`${rowIndex}-${cellIndex}`}>{cell}</TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Section>
  );
}
