/**
 * Types for the Craft Loops feature. Mirrors the serialization in
 * `backend/onyx/server/features/build/loops/api.py`.
 */

export type LoopState = "enabled" | "paused" | "quarantined" | "archived";

export type LoopHealth = "healthy" | "degraded" | "failing" | "quarantined";

export type LoopItemStatus =
  | "queued"
  | "in_progress"
  | "ready"
  | "shipped"
  | "failed"
  | "skipped";

export type LoopOutputState =
  | "staged"
  | "ready"
  | "shipping"
  | "shipped"
  | "returned";

export interface ShipActionSpec {
  action: string;
  gate: "hold" | "auto";
}

export interface LoopListItem {
  id: string;
  name: string;
  description: string;
  playbook: Record<string, unknown>;
  ship_actions: ShipActionSpec[];
  success_condition: string;
  caps: Record<string, unknown>;
  state: LoopState;
  health: LoopHealth;
  policy_version: number;
  consecutive_failed_fires: number;
  trigger_cron: string | null;
  next_fire_at: string | null;
  scenario_id: string | null;
  created_at: string;
  counts: Record<LoopItemStatus, number>;
}

export interface LoopItem {
  id: string;
  source_key: string;
  source_summary: string;
  status: LoopItemStatus;
  attempts: number;
  guidance: string | null;
  created_at: string;
}

export interface LoopOutput {
  id: string;
  item_id: string;
  ship_action: string;
  label: string | null;
  title: string;
  summary: string;
  state: LoopOutputState;
  decided_by: string | null;
  decided_at: string | null;
}

export interface LoopGrant {
  id: string;
  ship_action: string;
  label: string | null;
  policy_version: number;
  created_at: string;
  revoked_at: string | null;
}

export type OutputDecision = "ship" | "return";
