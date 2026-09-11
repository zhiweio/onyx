import type {
  AnyCatalogItem,
  CatalogItem,
  CatalogListResponse,
  ForkResponse,
  GalleryKind,
  SystemCatalogCategory,
  SystemCatalogPublishStatus,
  SystemReportTemplateItem,
  SystemScenarioItem,
  SystemSkillItem,
} from "@/lib/system-catalog/types";

const GALLERY_URL = "/api/craft/gallery";
const ADMIN_URL = "/api/admin/craft/catalog";

export class SystemCatalogRequestError extends Error {
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
    // Body was not JSON; fall through to the status message.
  }
  return `Request failed: ${response.status}`;
}

async function handle<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new SystemCatalogRequestError(
      await readError(response),
      response.status,
    );
  }
  if (response.status === 204) {
    // SAFETY: DELETE endpoints return an empty body; callers use Promise<void>.
    return undefined as T;
  }
  // SAFETY: FastAPI serializes the matching Pydantic response for this T.
  return (await response.json()) as T;
}

async function postJson<T>(url: string, body: unknown): Promise<T> {
  return handle<T>(
    await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

// ── gallery (read-only + fork) ──────────────────────────────────────────────

export function galleryListKey(
  kind: GalleryKind,
  filters?: { query?: string; category?: SystemCatalogCategory },
): string {
  const params = new URLSearchParams();
  if (filters?.query) params.set("q", filters.query);
  if (filters?.category) params.set("category", filters.category);
  const suffix = params.toString();
  return suffix ? `${GALLERY_URL}/${kind}?${suffix}` : `${GALLERY_URL}/${kind}`;
}

export function galleryDetailKey(kind: GalleryKind, entryId: string): string {
  return `${GALLERY_URL}/${kind}/${entryId}`;
}

export async function listGallerySkills(): Promise<SystemSkillItem[]> {
  const payload = await handle<CatalogListResponse<SystemSkillItem>>(
    await fetch(galleryListKey("skills")),
  );
  return payload.items;
}

export async function listGalleryScenarios(): Promise<SystemScenarioItem[]> {
  const payload = await handle<CatalogListResponse<SystemScenarioItem>>(
    await fetch(galleryListKey("scenarios")),
  );
  return payload.items;
}

export async function listGalleryReportTemplates(): Promise<
  SystemReportTemplateItem[]
> {
  const payload = await handle<CatalogListResponse<SystemReportTemplateItem>>(
    await fetch(galleryListKey("report-templates")),
  );
  return payload.items;
}

export async function getGalleryItem<T extends AnyCatalogItem>(
  kind: GalleryKind,
  entryId: string,
): Promise<T> {
  return handle<T>(await fetch(galleryDetailKey(kind, entryId)));
}

export async function forkGalleryItem(
  kind: GalleryKind,
  entryId: string,
): Promise<ForkResponse> {
  return handle<ForkResponse>(
    await fetch(`${GALLERY_URL}/${kind}/${entryId}/fork`, { method: "POST" }),
  );
}

// ── admin catalog ───────────────────────────────────────────────────────────

export function adminCatalogListKey(kind: GalleryKind): string {
  return `${ADMIN_URL}/${kind}`;
}

export function adminCatalogDetailKey(
  kind: GalleryKind,
  entryId: string,
): string {
  return `${ADMIN_URL}/${kind}/${entryId}`;
}

export async function getCatalogEntry<T extends CatalogItem>(
  kind: GalleryKind,
  entryId: string,
): Promise<T> {
  return handle<T>(await fetch(adminCatalogDetailKey(kind, entryId)));
}

export async function listCatalogEntries<T extends CatalogItem>(
  kind: GalleryKind,
): Promise<T[]> {
  const payload = await handle<CatalogListResponse<T>>(
    await fetch(adminCatalogListKey(kind)),
  );
  return payload.items;
}

export interface CatalogSkillCreateInput {
  slug: string;
  name: string;
  description: string;
  category: SystemCatalogCategory;
  tags: string[];
  built_in_skill_id: string;
}

export interface CatalogScenarioCreateInput {
  slug: string;
  name: string;
  description: string;
  category: SystemCatalogCategory;
  tags: string[];
  rules: Record<string, unknown>;
  skill_slugs: string[];
  report_template_slug: string | null;
}

export interface CatalogReportTemplateCreateInput {
  slug: string;
  name: string;
  description: string;
  body: string;
  category: SystemCatalogCategory;
  tags: string[];
}

export type CatalogCreateInput =
  | CatalogSkillCreateInput
  | CatalogScenarioCreateInput
  | CatalogReportTemplateCreateInput;

export interface CatalogPatchInput {
  name?: string;
  description?: string;
  category?: SystemCatalogCategory;
  tags?: string[];
  body?: string;
  rules?: Record<string, unknown>;
  skill_slugs?: string[];
  report_template_slug?: string | null;
  clear_report_template?: boolean;
}

export async function createCatalogEntry<T extends CatalogItem>(
  kind: GalleryKind,
  input: CatalogCreateInput,
): Promise<T> {
  return postJson<T>(`${ADMIN_URL}/${kind}`, input);
}

export async function updateCatalogEntry<T extends CatalogItem>(
  kind: GalleryKind,
  entryId: string,
  input: CatalogPatchInput,
): Promise<T> {
  return handle<T>(
    await fetch(`${ADMIN_URL}/${kind}/${entryId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }),
  );
}

export async function publishCatalogEntry<T extends CatalogItem>(
  kind: GalleryKind,
  entryId: string,
  changelog: string,
): Promise<T> {
  return postJson<T>(`${ADMIN_URL}/${kind}/${entryId}/publish`, { changelog });
}

export async function unpublishCatalogEntry<T extends CatalogItem>(
  kind: GalleryKind,
  entryId: string,
): Promise<T> {
  return handle<T>(
    await fetch(`${ADMIN_URL}/${kind}/${entryId}/unpublish`, {
      method: "POST",
    }),
  );
}

export async function deleteCatalogEntry(
  kind: GalleryKind,
  entryId: string,
): Promise<void> {
  await handle<void>(
    await fetch(`${ADMIN_URL}/${kind}/${entryId}`, { method: "DELETE" }),
  );
}

export async function uploadCatalogSkillBundle(input: {
  bundle: File;
  slug: string;
  category: SystemCatalogCategory;
  tags: string[];
}): Promise<SystemSkillItem> {
  const form = new FormData();
  form.append("bundle", input.bundle);
  form.append("slug", input.slug);
  form.append("category", input.category);
  form.append("tags", input.tags.join(","));
  return handle<SystemSkillItem>(
    await fetch(`${ADMIN_URL}/skills/upload`, { method: "POST", body: form }),
  );
}

export async function uploadCatalogReportTemplateDocx(
  entryId: string,
  file: File,
): Promise<SystemReportTemplateItem> {
  const form = new FormData();
  form.append("asset", file);
  return handle<SystemReportTemplateItem>(
    await fetch(`${ADMIN_URL}/report-templates/${entryId}/docx`, {
      method: "POST",
      body: form,
    }),
  );
}

export function catalogReportTemplateDocxUrl(entryId: string): string {
  return `${ADMIN_URL}/report-templates/${entryId}/docx`;
}

export function galleryReportTemplateDocxUrl(entryId: string): string {
  return `${GALLERY_URL}/report-templates/${entryId}/docx`;
}

export type { SystemCatalogPublishStatus };
