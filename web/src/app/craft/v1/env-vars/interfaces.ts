/**
 * Shared types for the env vars / secrets feature.
 *
 * These mirror the backend Pydantic models defined in
 * ``backend/onyx/server/features/build/env_vars/models.py``.
 */

export type EnvVarScope = "USER" | "PROJECT";

export interface EnvVarItem {
  id: string;
  name: string;
  is_secret: boolean;
  scope: EnvVarScope;
  project_id: string | null;
  project_name: string | null;
  /** Present only for non-secrets — secret values are write-only. */
  value: string | null;
  /** Whether the caller may edit / delete the row. */
  manageable: boolean;
  created_at: string;
  updated_at: string;
}

export interface EnvVarListResponse {
  items: EnvVarItem[];
}

export interface EnvVarCreateBody {
  name: string;
  value: string;
  is_secret: boolean;
  scope: EnvVarScope;
  project_id?: string | null;
}

export interface EnvVarPatchBody {
  name?: string;
  value?: string;
}
