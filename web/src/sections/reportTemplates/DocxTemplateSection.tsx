"use client";

import { useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { Button, Tag, Text } from "@opal/components";
import { Content, toast } from "@opal/layouts";
import {
  SvgCheck,
  SvgDownload,
  SvgEye,
  SvgFileText,
  SvgUploadCloud,
  SvgX,
} from "@opal/icons";
import {
  previewReportTemplateDocx,
  reportTemplateDocxUrl,
  uploadReportTemplateDocx,
} from "@/lib/report-templates/api";
import {
  isContractStyle,
  isDocxReportTemplate,
  type ReportContract,
  type ReportTemplateFinding,
  type ReportTemplateKind,
  type ReportTemplatePreviewResponse,
  type ReportTheme,
} from "@/lib/report-templates/types";

export interface DocxTemplateFields {
  id: string;
  slug: string;
  body: string;
  kind: ReportTemplateKind;
  asset_filename: string | null;
  contract?: ReportContract;
  theme?: ReportTheme;
}

const DOCX_MIME =
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

const DOCX_ACCEPT = `${DOCX_MIME},.docx`;

interface DocxTemplateSectionProps {
  template: DocxTemplateFields;
  disabled: boolean;
  onUploaded: (template: DocxTemplateFields) => void;
  upload?: (id: string, file: File) => Promise<DocxTemplateFields>;
  downloadUrl?: (id: string) => string;
  preview?: (
    body: string,
    contract?: ReportContract,
    theme?: ReportTheme
  ) => Promise<ReportTemplatePreviewResponse>;
  compact?: boolean;
}

/** Decode a base64 docx and hand it to the browser as a download. */
function downloadDocx(base64: string, filename: string) {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  const url = URL.createObjectURL(new Blob([bytes], { type: DOCX_MIME }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

/**
 * Attach an optional Word layout. The agent uses this file as the report
 * reference. Placeholders are not edited in the UI. Contract-style templates
 * show their contract summary and can render a preview sample instead.
 */
export default function DocxTemplateSection({
  template,
  disabled,
  onUploaded,
  upload = uploadReportTemplateDocx,
  downloadUrl = reportTemplateDocxUrl,
  preview = previewReportTemplateDocx,
  compact = false,
}: DocxTemplateSectionProps) {
  const t = useTranslations("craft.reportTemplates");
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [findings, setFindings] = useState<ReportTemplateFinding[] | null>(
    null
  );
  const isDocx = isDocxReportTemplate(template);
  const contractStyle = isContractStyle(template);
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

  async function handlePreview() {
    setPreviewing(true);
    try {
      const result = await preview(
        template.body,
        template.contract,
        template.theme
      );
      downloadDocx(result.docx_base64, `${template.slug}.docx`);
      setFindings(result.findings);
    } catch (previewError) {
      console.error(previewError);
      toast.error(
        previewError instanceof Error
          ? previewError.message
          : t("editor.docx.previewFailed.message")
      );
    } finally {
      setPreviewing(false);
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
      {contractStyle && (
        <Button
          prominence="tertiary"
          size="sm"
          icon={SvgEye}
          disabled={previewing}
          onClick={() => void handlePreview()}
        >
          {previewing
            ? t("editor.docx.previewing.label")
            : t("editor.docx.previewButton.label")}
        </Button>
      )}
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

      {contractStyle && (
        <div
          className="flex flex-wrap items-center gap-2"
          data-testid="DocxTemplateSection/contract"
        >
          <Tag
            size="sm"
            color="amber"
            title={t("editor.docx.contract.label")}
          />
          <Text font="secondary-body" color="text-03">
            {t("editor.docx.requiredElements.label", {
              count: template.contract?.required_elements?.length ?? 0,
            })}
          </Text>
          {template.theme?.accent && (
            <span
              className="size-2.5 shrink-0 rounded-full border border-border-02"
              style={{ backgroundColor: `#${template.theme.accent}` }}
              title={`#${template.theme.accent}`}
              data-testid="DocxTemplateSection/themeAccent"
            />
          )}
        </div>
      )}

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

      {findings && findings.length > 0 && (
        <div className="flex flex-col gap-1.5 rounded-12 border border-border-01 bg-background-neutral-01 px-3 py-2.5">
          <Text font="main-ui-action" color="text-04">
            {t("editor.docx.findings.title")}
          </Text>
          <ul
            className="flex flex-col gap-1"
            data-testid="DocxTemplateSection/findings"
          >
            {findings.map((finding) => (
              <li key={finding.check} className="flex items-start gap-1.5">
                {finding.passed ? (
                  <SvgCheck className="mt-0.5 size-3.5 shrink-0 text-status-success-05" />
                ) : (
                  <SvgX className="mt-0.5 size-3.5 shrink-0 text-status-error-05" />
                )}
                <Text
                  font="secondary-body"
                  color={finding.passed ? "text-03" : "status-error-05"}
                >
                  {finding.check}
                </Text>
                <Text
                  font="secondary-body"
                  color={finding.passed ? "text-04" : "status-error-05"}
                >
                  {finding.detail}
                </Text>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
