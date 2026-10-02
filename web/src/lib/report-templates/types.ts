export type ReportTemplateKind = "MARKDOWN" | "DOCX";

/**
 * Content contract for contract-style templates. An empty object means the
 * legacy layout-reference behaviour (see backend ReportContract).
 */
export interface ReportContract {
  must_answer?: string[];
  required_elements?: string[];
  spine?: string[];
  components?: string[];
  hard_rules?: string[];
  completion_criteria?: string[];
  min_figures?: number;
  require_toc?: boolean;
  require_disclaimer?: boolean;
}

/**
 * Visual tokens the deterministic docx renderer applies. Colors are six-digit
 * RGB hex without the leading "#" (see backend ReportTheme).
 */
export interface ReportTheme {
  accent?: string;
  ink?: string;
  muted?: string;
  alert?: string;
  positive?: string;
  band?: string;
  font_latin?: string;
  font_east_asia?: string;
  heading_font_latin?: string;
  heading_font_east_asia?: string;
  cover?: "centered" | "banner";
}

/** One deterministic postcheck outcome of a rendered sample document. */
export interface ReportTemplateFinding {
  check: string;
  passed: boolean;
  detail: string;
}

export interface ReportTemplatePreviewResponse {
  docx_base64: string;
  findings: ReportTemplateFinding[];
}

export interface ReportTemplate {
  id: string;
  slug: string;
  name: string;
  description: string;
  body: string;
  kind: ReportTemplateKind;
  asset_filename: string | null;
  author_user_id: string | null;
  is_builtin: boolean;
  referenced_count: number;
  can_edit: boolean;
  can_delete: boolean;
  contract: ReportContract;
  theme: ReportTheme;
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

/** True when the template opts into the contract+renderer scheme. */
export function isContractStyle(template: {
  contract?: ReportContract | null;
}): boolean {
  return !!template.contract && Object.keys(template.contract).length > 0;
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

/** Path the agent reads the pushed template from inside the sandbox. */
export function sandboxTemplatePath(template: { slug: string }): string {
  return `/workspace/managed/report_templates/${template.slug}.docx`;
}
