export type ReportTemplateKind = "MARKDOWN" | "DOCX";

export type PlaceholderKind = "text" | "multiline" | "date" | "number" | "table";

export interface PlaceholderSpec {
  name: string;
  kind: PlaceholderKind;
  required: boolean;
  description: string;
  example: string;
}

export interface ReportTemplate {
  id: string;
  slug: string;
  name: string;
  description: string;
  body: string;
  kind: ReportTemplateKind;
  /** Extracted from the uploaded .docx, so it always matches the real file. */
  placeholders: PlaceholderSpec[];
  asset_filename: string | null;
  author_user_id: string | null;
  is_builtin: boolean;
  referenced_count: number;
  can_edit: boolean;
  can_delete: boolean;
  created_at: string;
  updated_at: string;
}

export interface ReportTemplateListResponse {
  templates: ReportTemplate[];
}

export interface ReportTemplateUpsert {
  name: string;
  slug?: string | null;
  description?: string;
  body: string;
}

export function isWorkspaceReportTemplate(template: ReportTemplate): boolean {
  return template.author_user_id === null;
}

export function suggestReportTemplateSlug(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 64);
}

export function canEditReportTemplate(template: ReportTemplate): boolean {
  return template.can_edit;
}

export function canDeleteReportTemplate(template: ReportTemplate): boolean {
  return template.can_delete;
}

export function isDocxReportTemplate(template: {
  kind: ReportTemplateKind;
}): boolean {
  return template.kind === "DOCX";
}

export function placeholderToken(spec: PlaceholderSpec): string {
  return `{{${spec.name}}}`;
}

/** Path the agent reads the pushed template from inside the sandbox. */
export function sandboxTemplatePath(template: { slug: string }): string {
  return `/workspace/managed/report_templates/${template.slug}.docx`;
}
