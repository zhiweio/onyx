/**
 * Prompt history: pure navigation logic (ported from ZCode) plus the
 * localStorage persistence Onyx layers on top.
 *
 * Navigation only takes over the arrow keys while the editor is empty or a
 * history entry is already being browsed, so multi-line cursor movement is
 * never hijacked.
 */

export const MAX_PROMPT_HISTORY = 30;

type PromptHistoryDirection = "up" | "down";

interface PromptHistoryNavigationResult {
  nextIndex: number | null;
  nextValue: string;
  shouldHandle: boolean;
}

export function appendPromptHistoryEntry(
  entries: readonly string[],
  entry: string,
  limit = MAX_PROMPT_HISTORY,
): string[] {
  const trimmed = entry.trim();
  if (!trimmed) {
    return [...entries];
  }
  // Only suppress consecutive duplicates so A, B, A stays intact.
  if (entries.at(-1)?.trim() === trimmed) {
    return [...entries];
  }
  const normalizedLimit = Math.max(1, Math.trunc(limit));
  return [...entries, trimmed].slice(-normalizedLimit);
}

export function navigatePromptHistory(
  entries: readonly string[],
  currentIndex: number | null,
  direction: PromptHistoryDirection,
): PromptHistoryNavigationResult {
  if (entries.length === 0) {
    return { nextIndex: currentIndex, nextValue: "", shouldHandle: false };
  }

  if (direction === "up") {
    const nextIndex =
      currentIndex === null
        ? entries.length - 1
        : Math.max(currentIndex - 1, 0);
    return {
      nextIndex,
      nextValue: entries[nextIndex] ?? "",
      shouldHandle: true,
    };
  }

  if (currentIndex === null) {
    const nextIndex = entries.length - 1;
    return {
      nextIndex,
      nextValue: entries[nextIndex] ?? "",
      shouldHandle: true,
    };
  }

  if (currentIndex >= entries.length - 1) {
    // Down past the newest entry exits history browsing and empties the draft,
    // matching terminal-style prompt history.
    return { nextIndex: null, nextValue: "", shouldHandle: true };
  }

  const nextIndex = currentIndex + 1;
  return {
    nextIndex,
    nextValue: entries[nextIndex] ?? "",
    shouldHandle: true,
  };
}

function getStorage(): Storage | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function isValidHistory(value: unknown): value is string[] {
  return (
    Array.isArray(value) && value.every((entry) => typeof entry === "string")
  );
}

export function readStoredPromptHistory(storageKey: string): string[] {
  const storage = getStorage();
  if (!storage) return [];
  try {
    const raw = storage.getItem(storageKey);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return isValidHistory(parsed) ? parsed.slice(-MAX_PROMPT_HISTORY) : [];
  } catch {
    return [];
  }
}

/** Persist one submitted prompt; returns the resulting in-memory history. */
export function appendStoredPromptHistory(
  storageKey: string,
  entry: string,
): string[] {
  const next = appendPromptHistoryEntry(
    readStoredPromptHistory(storageKey),
    entry,
  );
  const storage = getStorage();
  try {
    storage?.setItem(storageKey, JSON.stringify(next));
  } catch {
    // Quota / private mode: history simply does not persist.
  }
  return next;
}
