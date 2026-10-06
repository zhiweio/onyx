import type { TapeSessionItem, TapeTurnItem } from "@/lib/craft-tape/types";

/**
 * dsh SessionStatus semantics ported to tapes: live activity outranks
 * failure, failure outranks an ambiguous stop, a clean finish outranks idle.
 * An open turn (no end reason yet) is the running state; a dead runner gets
 * reclassified as `interrupted` server-side, so null reliably means live.
 */
export type TapeStatus = "running" | "error" | "warning" | "done" | "idle";

export function sessionTapeStatus(item: TapeSessionItem): TapeStatus {
  if (item.last_reason === null && item.turns > 0) return "running";
  return reasonTapeStatus(item.last_reason);
}

export function turnTapeStatus(
  turn: Pick<TapeTurnItem, "turn_end_reason">
): TapeStatus {
  if (turn.turn_end_reason === null) return "running";
  return reasonTapeStatus(turn.turn_end_reason);
}

function reasonTapeStatus(reason: string | null): TapeStatus {
  switch (reason) {
    case "completed":
      return "done";
    case "error":
    case "deadline_exceeded":
      return "error";
    case "aborted":
    case "interrupted":
      return "warning";
    default:
      return "idle";
  }
}
