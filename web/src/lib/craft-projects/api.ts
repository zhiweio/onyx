import type {
  CraftProject,
  CraftProjectFile,
  CraftProjectListResponse,
  CraftProjectUpsert,
} from "@/lib/craft-projects/types";
import {
  PROJECT_FILE_TEXT_PREVIEW_MAX_BYTES,
  projectFilePreviewKind,
} from "@/lib/craft-projects/display";

const PROJECTS_URL = "/api/craft-projects";

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
    throw new Error(await readError(response));
  }
  if (response.status === 204) {
    // SAFETY: DELETE endpoints return an empty body; callers use Promise<void>.
    return undefined as T;
  }
  // SAFETY: FastAPI serializes the matching Pydantic response for this T.
  return (await response.json()) as T;
}

export async function listCraftProjects(): Promise<CraftProject[]> {
  const response = await fetch(PROJECTS_URL);
  const payload = await handle<CraftProjectListResponse>(response);
  return payload.projects;
}

export async function getCraftProject(projectId: string): Promise<CraftProject> {
  const response = await fetch(`${PROJECTS_URL}/${projectId}`);
  return handle<CraftProject>(response);
}

export async function createCraftProject(
  body: CraftProjectUpsert
): Promise<CraftProject> {
  const response = await fetch(PROJECTS_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return handle<CraftProject>(response);
}

export async function updateCraftProject(
  projectId: string,
  body: Partial<CraftProjectUpsert>
): Promise<CraftProject> {
  const response = await fetch(`${PROJECTS_URL}/${projectId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return handle<CraftProject>(response);
}

export async function deleteCraftProject(projectId: string): Promise<void> {
  const response = await fetch(`${PROJECTS_URL}/${projectId}`, {
    method: "DELETE",
  });
  await handle<void>(response);
}

export async function uploadCraftProjectFile(
  projectId: string,
  file: File
): Promise<CraftProjectFile> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(`${PROJECTS_URL}/${projectId}/files`, {
    method: "POST",
    body: form,
  });
  return handle<CraftProjectFile>(response);
}

export function craftProjectFileUrl(
  projectId: string,
  fileId: string
): string {
  return `${PROJECTS_URL}/${projectId}/files/${fileId}`;
}

export type CraftProjectFilePreviewPayload =
  | { status: "text"; text: string }
  | { status: "image"; blob: Blob }
  | { status: "too-large"; sizeBytes: number }
  | { status: "unsupported" };

export async function fetchCraftProjectFileContent(
  projectId: string,
  file: CraftProjectFile
): Promise<CraftProjectFilePreviewPayload> {
  const kind = projectFilePreviewKind(file);
  if (kind === "unsupported") {
    return { status: "unsupported" };
  }
  const knownSize = file.size_bytes ?? 0;
  if (kind !== "image" && knownSize > PROJECT_FILE_TEXT_PREVIEW_MAX_BYTES) {
    return { status: "too-large", sizeBytes: knownSize };
  }

  const response = await fetch(craftProjectFileUrl(projectId, file.id));
  if (!response.ok) {
    throw new Error(await readError(response));
  }
  const length = Number(response.headers.get("content-length") ?? 0);
  if (kind !== "image" && length > PROJECT_FILE_TEXT_PREVIEW_MAX_BYTES) {
    return { status: "too-large", sizeBytes: length };
  }
  if (kind === "image") {
    return { status: "image", blob: await response.blob() };
  }
  return { status: "text", text: await response.text() };
}

export async function deleteCraftProjectFile(
  projectId: string,
  fileId: string
): Promise<void> {
  const response = await fetch(`${PROJECTS_URL}/${projectId}/files/${fileId}`, {
    method: "DELETE",
  });
  await handle<void>(response);
}

export async function startCraftProjectSession(
  projectId: string,
  name?: string
): Promise<{ id: string }> {
  const response = await fetch(`${PROJECTS_URL}/${projectId}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: name ?? null, headless: false }),
  });
  return handle<{ id: string }>(response);
}
