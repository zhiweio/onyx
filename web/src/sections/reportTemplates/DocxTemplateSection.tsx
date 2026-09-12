"use client";

import { useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { Button, MessageCard } from "@opal/components";
import { FileUpload } from "@/sections/extend/file-upload";
import { SchemaBuilderPanel } from "@/sections/extend/schema-builder";
import { placeholdersToSchema } from "@/sections/reportTemplates/placeholdersToSchema";
import { Content, InputVertical, toast } from "@opal/layouts";
import { SvgDownload, SvgUploadCloud } from "@opal/icons";
import {
  reportTemplateDocxUrl,
  uploadReportTemplateDocx,
} from "@/lib/report-templates/api";
import {
  isDocxReportTemplate,
  sandboxTemplatePath,
  type PlaceholderSpec,
  type ReportTemplateKind,
} from "@/lib/report-templates/types";

export interface DocxTemplateFields {
  id: string;
  slug: string;
  kind: ReportTemplateKind;
  placeholders: PlaceholderSpec[];
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
}

/**
 * Attach a Word document to a report template.
 *
 * Placeholders are read from the uploaded file by the server, so this shows
 * what the agent will actually be asked to fill rather than a hand-kept list.
 */
export default function DocxTemplateSection({
  template,
  disabled,
  onUploaded,
  upload = uploadReportTemplateDocx,
  downloadUrl = reportTemplateDocxUrl,
}: DocxTemplateSectionProps) {
  const t = useTranslations("craft.reportTemplates");
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const isDocx = isDocxReportTemplate(template);

  async function handleFile(file: File | undefined) {
    if (!file) return;
    setUploading(true);
    try {
      const updated = await upload(template.id, file);
      onUploaded(updated);
      toast.success(
        t("editor.docx.uploaded.message", {
          count: updated.placeholders.length,
        })
      );
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

  return (
    <InputVertical withLabel title={t("editor.docx.title")}>
      <Content
        title={t("editor.docx.hint")}
        sizePreset="secondary"
        variant="body"
        color="muted"
      />

      {isDocx && (
        <MessageCard
          variant="info"
          title={template.asset_filename ?? `${template.slug}.docx`}
          description={t("editor.docx.sandboxPath.description", {
            path: sandboxTemplatePath(template),
          })}
        />
      )}

      <div className="flex flex-col gap-3">
        {!disabled && (
          <FileUpload
            accept={DOCX_ACCEPT}
            multiple={false}
            showBorderBeam={false}
            showFileList={false}
            title={
              isDocx
                ? t("editor.docx.replaceButton.label")
                : t("editor.docx.uploadButton.label")
            }
            description={t("editor.docx.hint")}
            onFilesAccepted={(files) => void handleFile(files[0])}
          />
        )}
        <div className="flex flex-row flex-wrap items-center gap-2">
          <input
            ref={inputRef}
            type="file"
            accept={DOCX_ACCEPT}
            className="hidden"
            data-testid="DocxTemplateSection/input"
            onChange={(event) => void handleFile(event.target.files?.[0])}
          />
          <Button
            prominence="secondary"
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
              icon={SvgDownload}
              href={downloadUrl(template.id)}
            >
              {t("editor.docx.downloadButton.label")}
            </Button>
          )}
        </div>
      </div>

      {isDocx && (
        <div className="flex flex-col gap-2">
          <Content
            title={t("editor.docx.placeholders.title", {
              count: template.placeholders.length,
            })}
            sizePreset="secondary"
            variant="body"
          />
          {template.placeholders.length > 0 ? (
            <SchemaBuilderPanel
              schema={placeholdersToSchema(template.placeholders)}
            />
          ) : (
            <Content
              title={t("editor.docx.placeholders.none")}
              sizePreset="secondary"
              variant="body"
              color="muted"
            />
          )}
        </div>
      )}
    </InputVertical>
  );
}
