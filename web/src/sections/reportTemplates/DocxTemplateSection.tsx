"use client";

import { useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { Button, Text } from "@opal/components";
import { Content, toast } from "@opal/layouts";
import { SvgDownload, SvgFileText, SvgUploadCloud } from "@opal/icons";
import {
  reportTemplateDocxUrl,
  uploadReportTemplateDocx,
} from "@/lib/report-templates/api";
import {
  isDocxReportTemplate,
  type ReportTemplateKind,
} from "@/lib/report-templates/types";

export interface DocxTemplateFields {
  id: string;
  slug: string;
  kind: ReportTemplateKind;
  asset_filename: string | null;
}

const DOCX_ACCEPT =
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document,.docx";

interface DocxTemplateSectionProps {
  template: DocxTemplateFields;
  disabled: boolean;
  onUploaded: (template: DocxTemplateFields) => void;
  upload?: (id: string, file: File) => Promise<DocxTemplateFields>;
  downloadUrl?: (id: string) => string;
  compact?: boolean;
}

/**
 * Attach an optional Word layout. The agent uses this file as the report
 * reference. Placeholders are not edited in the UI.
 */
export default function DocxTemplateSection({
  template,
  disabled,
  onUploaded,
  upload = uploadReportTemplateDocx,
  downloadUrl = reportTemplateDocxUrl,
  compact = false,
}: DocxTemplateSectionProps) {
  const t = useTranslations("craft.reportTemplates");
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const isDocx = isDocxReportTemplate(template);
  const filename = template.asset_filename ?? `${template.slug}.docx`;

  async function handleFile(file: File | undefined) {
    if (!file) return;
    setUploading(true);
    try {
      const updated = await upload(template.id, file);
      onUploaded(updated);
      toast.success(t("editor.docx.uploaded.message"));
    } catch (uploadError) {
      console.error(uploadError);
      toast.error(
        uploadError instanceof Error
          ? uploadError.message
          : t("editor.docx.uploadFailed.message")
      );
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  const fileActions = (
    <div className="flex shrink-0 flex-row flex-wrap items-center gap-1">
      <input
        ref={inputRef}
        type="file"
        accept={DOCX_ACCEPT}
        className="hidden"
        data-testid="DocxTemplateSection/input"
        onChange={(event) => void handleFile(event.target.files?.[0])}
      />
      <Button
        prominence={isDocx ? "tertiary" : "secondary"}
        size="sm"
        icon={SvgUploadCloud}
        disabled={disabled || uploading}
        onClick={() => inputRef.current?.click()}
      >
        {isDocx
          ? t("editor.docx.replaceButton.label")
          : t("editor.docx.uploadButton.label")}
      </Button>
      {isDocx && (
        <Button
          prominence="tertiary"
          size="sm"
          icon={SvgDownload}
          href={downloadUrl(template.id)}
        >
          {t("editor.docx.downloadButton.label")}
        </Button>
      )}
    </div>
  );

  return (
    <div className="flex flex-col gap-2">
      <Content
        title={t("editor.docx.title")}
        description={compact ? undefined : t("editor.docx.hint")}
        sizePreset="secondary"
        variant="section"
      />

      {isDocx ? (
        <div className="flex flex-row flex-wrap items-center justify-between gap-3 rounded-12 border border-border-01 bg-background-neutral-01 px-3 py-2.5">
          <div className="flex min-w-0 flex-1 items-center gap-3">
            <div className="flex size-9 shrink-0 items-center justify-center rounded-08 bg-background-neutral-02 text-text-03">
              <SvgFileText className="size-4" />
            </div>
            <Text font="main-ui-action" color="text-04">
              {filename}
            </Text>
          </div>
          {fileActions}
        </div>
      ) : (
        <div className="flex flex-row flex-wrap items-center justify-between gap-3 rounded-12 border border-dashed border-border-02 bg-background-neutral-01 px-3 py-2.5">
          <Text font="secondary-body" color="text-03">
            {t("editor.docx.hint")}
          </Text>
          {fileActions}
        </div>
      )}
    </div>
  );
}
