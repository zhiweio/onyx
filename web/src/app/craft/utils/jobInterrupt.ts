export type CraftComposerStopKind = "cancel-job" | "interrupt-turn";

/**
 * The composer stop control. A long job in flight uses the same cancel path
 * as the header Cancel button (parent session plus specialist lanes).
 */
export function craftComposerStopKind(input: {
  jobInFlight: boolean;
  scheduledRunInFlight: boolean;
  sessionStatus?: string | null;
}): CraftComposerStopKind | null {
  if (input.scheduledRunInFlight) {
    return null;
  }
  if (input.jobInFlight) {
    return "cancel-job";
  }
  if (input.sessionStatus === "running") {
    return "interrupt-turn";
  }
  return null;
}
