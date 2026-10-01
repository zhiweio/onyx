/**
 * Module-level persisted open state for tool blocks, ported from ZCode's
 * ToolLayout: collapse decisions survive re-renders and remounts (history
 * reloads, session switches) keyed by tool call id. Bounded to avoid
 * unbounded growth on very long sessions.
 */

const MAX_TRACKED_OPEN_STATES = 2000;

export const toolLayoutOpenState = new Map<string, boolean>();

export function getToolLayoutOpen(key: string): boolean | undefined {
  return toolLayoutOpenState.get(key);
}

export function setToolLayoutOpen(key: string, open: boolean): void {
  if (
    toolLayoutOpenState.size >= MAX_TRACKED_OPEN_STATES &&
    !toolLayoutOpenState.has(key)
  ) {
    // Drop the oldest entry (insertion order) once the cap is hit.
    const oldest = toolLayoutOpenState.keys().next().value;
    if (oldest !== undefined) {
      toolLayoutOpenState.delete(oldest);
    }
  }
  toolLayoutOpenState.set(key, open);
}

/** Collapse animation reads the Radix height variable while closing; children
 * must stay mounted briefly or the animation collapses from a stale height. */
export const TOOL_CONTENT_COLLAPSE_UNMOUNT_DELAY_MS = 300;
