export interface TapeSessionItem {
  session_id: string;
  name: string | null;
  user_id: string | null;
  user_email: string | null;
  origin: string | null;
  created_at: string | null;
  turns: number;
  events: number;
  hot_events: number;
  archived: boolean;
  input_tokens: number;
  output_tokens: number;
  cost: number;
  last_activity: string | null;
  last_reason: string | null;
  runtimes: string[];
}

export interface TapeSessionList {
  items: TapeSessionItem[];
  total: number;
}

export interface TapeTurnItem {
  turn_index: number;
  runtime: string;
  started_at: string | null;
  ended_at: string | null;
  event_count: number;
  input_tokens: number | null;
  output_tokens: number | null;
  cost: number | null;
  turn_end_reason: string | null;
  error_detail: string | null;
  model: string | null;
  tier: string;
}

export interface TapeTurnList {
  items: TapeTurnItem[];
  total: number;
}

export interface TapeEventItem {
  source_id: number;
  turn_index: number | null;
  kind: string;
  subtype: string;
  runtime: string;
  payload: Record<string, unknown>;
  created_at: string;
  annotations: string[];
}

export interface TapeEventList {
  items: TapeEventItem[];
  next_source_id: number | null;
}

export interface TapeStats {
  sessions: number;
  turns: number;
  events: number;
  input_tokens: number;
  output_tokens: number;
  cost: number;
  by_reason: Record<string, number>;
  by_runtime: Record<string, number>;
  archiving_enabled: boolean;
  hot_retention_days: number | null;
  lake_retention_days: number | null;
}

export interface TapeStatsSeriesPoint {
  day: string;
  sessions: number;
  turns: number;
  events: number;
}

export interface ReplayPacketItem {
  source_id: number;
  turn_index: number | null;
  created_at: string;
  type: "packet" | "marker";
  packet: Record<string, unknown> | null;
  marker: "turn_start" | "turn_end" | null;
  reason: string | null;
}

export interface ReplayPage {
  items: ReplayPacketItem[];
  next_source_id: number | null;
  skipped: number;
}
