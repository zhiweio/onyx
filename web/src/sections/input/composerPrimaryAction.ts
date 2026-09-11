export type ComposerPrimaryAction = "send" | "queue" | "stop" | "busy";

export interface ComposerPrimaryActionInput {
  /** A turn is in flight, or another stoppable activity is active. */
  isRunning: boolean;
  /** The composer has a non-empty draft. */
  hasText: boolean;
  /** A follow-up can be queued against the in-flight turn. */
  canQueue: boolean;
  /** The control should show a spinner and ignore clicks. */
  isBusy: boolean;
  /** The in-flight activity can be stopped from this button. */
  canStop: boolean;
}

/**
 * Cursor-style single composer button:
 * busy → spinner; running + draft → queue; running + empty → stop; else send.
 */
export function resolveComposerPrimaryAction(
  input: ComposerPrimaryActionInput
): ComposerPrimaryAction {
  if (input.isBusy) return "busy";
  if (input.isRunning && input.hasText && input.canQueue) return "queue";
  if (input.isRunning && input.canStop && !input.hasText) return "stop";
  return "send";
}
