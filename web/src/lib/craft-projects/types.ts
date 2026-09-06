export type CraftProjectFileSource = "upload" | "session_output";

export type CraftProjectSessionStatus =
  | "INITIALIZING"
  | "ACTIVE"
  | "IDLE"
  | "FAILED";

export interface CraftProjectFile {
  id: string;
  project_id: string;
  path: string;
  name: string;
  mime_type: string | null;
  size_bytes: number | null;
  content_hash: string | null;
  source: CraftProjectFileSource;
  produced_by_session_id: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface CraftProjectSession {
  id: string;
  name: string | null;
  status: CraftProjectSessionStatus;
  created_at: string;
  last_activity_at: string;
}

export interface CraftProject {
  id: string;
  name: string;
  description: string;
  instructions: string | null;
  file_count: number;
  session_count: number;
  created_at: string;
  updated_at: string;
  files?: CraftProjectFile[] | null;
  sessions?: CraftProjectSession[] | null;
}

export interface CraftProjectListResponse {
  projects: CraftProject[];
}

export interface CraftProjectUpsert {
  name: string;
  description?: string;
  instructions?: string | null;
}
