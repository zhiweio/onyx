import type {
  ReportTemplate,
  ReportTemplateListResponse,
  ReportTemplateUpsert,
} from "@/lib/report-templates/types";

const TEMPLATES_URL = "/api/report-templates";

export class ReportTemplateRequestError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") {
      return body.detail;
    }
  } catch {
    // ignore
  }
  return `Request failed: ${response.status}`;
}

async function handle<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new ReportTemplateRequestError(
      await readError(response),
      response.status
    );
  }
  if (response.status === 204) {
    // SAFETY: DELETE endpoints return an empty body; callers use Promise<void>.
    return undefined as T;
  }
  // SAFETY: FastAPI serializes the matching Pydantic response for this T.
  return (await response.json()) as T;
}

export async function listReportTemplates(): Promise<ReportTemplate[]> {
  const response = await fetch(TEMPLATES_URL);
  const payload = await handle<ReportTemplateListResponse>(response);
  return payload.templates;
}

export async function getReportTemplate(
  templateId: string
): Promise<ReportTemplate> {
  const response = await fetch(`${TEMPLATES_URL}/${templateId}`);
  return handle<ReportTemplate>(response);
}

export async function createReportTemplate(
  input: ReportTemplateUpsert
): Promise<ReportTemplate> {
  const response = await fetch(TEMPLATES_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return handle<ReportTemplate>(response);
}

export async function updateReportTemplate(
  templateId: string,
  input: Partial<ReportTemplateUpsert>
): Promise<ReportTemplate> {
  const response = await fetch(`${TEMPLATES_URL}/${templateId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return handle<ReportTemplate>(response);
}

export async function deleteReportTemplate(templateId: string): Promise<void> {
  const response = await fetch(`${TEMPLATES_URL}/${templateId}`, {
    method: "DELETE",
  });
  await handle<void>(response);
}
