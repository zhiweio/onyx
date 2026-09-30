export type ApprovalDecision = "APPROVED" | "REJECTED" | "EXPIRED";

// Server-only EXPIRED is excluded; clients can only submit a yes/no.
export type ApprovalSubmitDecision = "APPROVED" | "REJECTED";

// Mirrors backend `EndpointPolicy`. DENY blocks before persistence, so
// persisted entries are always ASK or ALWAYS — included only to match
// the backend enum exactly.
export type ApprovalActionPolicy = "ASK" | "ALWAYS" | "DENY";

// Mirrors backend `ActionMatch`.
export interface ApprovalAction {
  action_type: string;
  display_name: string;
  description: string;
  policy: ApprovalActionPolicy;
}

export interface ApprovalView {
  approval_id: string;
  session_id: string;
  // Non-empty, sorted strictest-policy-first; actions[0] drove the gate.
  actions: ApprovalAction[];
  app_name: string;
  payload: Record<string, unknown>;
  display_payload: Record<string, unknown>;
  created_at: string;
  decision: ApprovalDecision | null;
  decided_at: string | null;
  is_live: boolean;
}

// Mirrors backend `ContentQuarantineDecision` (client can only submit yes/no).
export type ContentQuarantineSubmitDecision = "APPROVED" | "DENIED";

// Mirrors backend `ContentReleaseScope`.
export type ContentReleaseScope = "ONCE" | "SESSION" | "HOST";

export interface ContentQuarantineView {
  quarantine_id: string;
  session_id: string;
  url_host: string;
  url_path: string;
  patterns_matched: string[];
  evidence_excerpt: string;
  created_at: string;
}

export interface ContentQuarantineListResponse {
  items: ContentQuarantineView[];
}

export interface ApprovalListResponse {
  items: ApprovalView[];
  content_quarantines: ContentQuarantineView[];
}
