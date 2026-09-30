import { errorHandlingFetcher } from "@/lib/fetcher";

export interface StandardAnswerCategoryRow {
  id: number;
  name: string;
}

export interface StandardAnswerRow {
  id: number;
  keyword: string;
  answer: string;
  active: boolean;
  match_regex: boolean;
  match_any_keywords: boolean;
  category_ids: number[];
}

export interface StandardAnswerListArgs {
  q: string;
  category_id: number | null;
  offset: number;
  limit: number;
}

export interface StandardAnswerListResult {
  items: StandardAnswerRow[];
  total_items: number;
}

export interface StandardAnswerCreateBody {
  keyword: string;
  answer: string;
  active?: boolean;
  match_regex?: boolean;
  match_any_keywords?: boolean;
  category_ids?: number[];
}

export interface StandardAnswerPatchBody {
  keyword?: string;
  answer?: string;
  active?: boolean;
  match_regex?: boolean;
  match_any_keywords?: boolean;
  category_ids?: number[];
}

function buildQuery(
  params: Record<string, string | number | undefined>
): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      query.set(key, String(value));
    }
  }
  const encoded = query.toString();
  return encoded ? `?${encoded}` : "";
}

export function fetchStandardAnswers(
  args: StandardAnswerListArgs
): Promise<StandardAnswerListResult> {
  return errorHandlingFetcher<StandardAnswerListResult>(
    `/api/admin/standard-answers${buildQuery({
      q: args.q || undefined,
      category_id: args.category_id ?? undefined,
      page_num: Math.floor(args.offset / args.limit),
      page_size: args.limit,
    })}`
  );
}

export function fetchStandardAnswerCategories(): Promise<
  StandardAnswerCategoryRow[]
> {
  return errorHandlingFetcher<StandardAnswerCategoryRow[]>(
    "/api/admin/standard-answers/categories"
  );
}

async function mutateJson<T>(path: string, init: RequestInit): Promise<T> {
  const resp = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json" },
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${resp.status}`);
  }
  return resp.json() as Promise<T>;
}

export function createStandardAnswer(
  body: StandardAnswerCreateBody
): Promise<StandardAnswerRow> {
  return mutateJson("/api/admin/standard-answers", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateStandardAnswer(
  answerId: number,
  patch: StandardAnswerPatchBody
): Promise<StandardAnswerRow> {
  return mutateJson(`/api/admin/standard-answers/${answerId}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export function deleteStandardAnswer(answerId: number): Promise<void> {
  return mutateJson(`/api/admin/standard-answers/${answerId}`, {
    method: "DELETE",
  });
}

export function createStandardAnswerCategory(
  name: string
): Promise<StandardAnswerCategoryRow> {
  return mutateJson("/api/admin/standard-answers/categories", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}
