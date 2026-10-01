import type { ComposerDraftSnapshot } from "@/sections/input/lexical/types";

/**
 * Per-scope composer draft persistence (localStorage). Scope is a session id
 * (or "__draft__" for a new conversation); surface separates craft from the
 * main chat so the two never share keys.
 *
 * Mirrors ZCode semantics: text + serialized editor state are persisted,
 * attachments are not (File objects are not serializable), submitting clears
 * the draft, and an all-empty draft removes the scope entirely.
 */

const STORAGE_KEY_PREFIX = "onyx-composer-draft:v1";

interface DraftFile {
  version: 1;
  scopes: Record<string, ComposerDraftSnapshot & { updatedAt: number }>;
}

function storageKey(surface: string, scope: string): string {
  return `${STORAGE_KEY_PREFIX}:${surface}:${encodeURIComponent(scope)}`;
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

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readDraftFile(key: string): DraftFile {
  const storage = getStorage();
  try {
    const raw = storage?.getItem(key);
    if (!raw) return { version: 1, scopes: {} };
    const parsed: unknown = JSON.parse(raw);
    if (!isRecord(parsed) || !isRecord(parsed.scopes)) {
      return { version: 1, scopes: {} };
    }
    const scopes: DraftFile["scopes"] = {};
    for (const [scopeId, value] of Object.entries(parsed.scopes)) {
      if (!isRecord(value) || typeof value.text !== "string") continue;
      if (
        value.editorStateJson !== undefined &&
        typeof value.editorStateJson !== "string"
      ) {
        continue;
      }
      scopes[scopeId] = {
        text: value.text,
        ...(typeof value.editorStateJson === "string"
          ? { editorStateJson: value.editorStateJson }
          : {}),
        updatedAt:
          typeof value.updatedAt === "number" &&
          Number.isFinite(value.updatedAt)
            ? value.updatedAt
            : 0,
      };
    }
    return { version: 1, scopes };
  } catch {
    return { version: 1, scopes: {} };
  }
}

function writeDraftFile(key: string, file: DraftFile): boolean {
  const storage = getStorage();
  if (!storage) return false;
  try {
    if (Object.keys(file.scopes).length === 0) {
      storage.removeItem(key);
      return true;
    }
    storage.setItem(key, JSON.stringify(file));
    return true;
  } catch {
    // Quota / private mode: degrade to no persistence.
    return false;
  }
}

export function readComposerDraft(
  surface: string,
  scope: string,
): ComposerDraftSnapshot | null {
  const draft = readDraftFile(storageKey(surface, scope)).scopes[scope];
  if (!draft || !draft.text.trim()) {
    return null;
  }
  return { text: draft.text, editorStateJson: draft.editorStateJson };
}

export function persistComposerDraft(
  surface: string,
  scope: string,
  draft: ComposerDraftSnapshot,
): boolean {
  const key = storageKey(surface, scope);
  const file = readDraftFile(key);
  if (!draft.text.trim() && !draft.editorStateJson) {
    delete file.scopes[scope];
  } else {
    file.scopes[scope] = { ...draft, updatedAt: Date.now() };
  }
  return writeDraftFile(key, file);
}

export function clearComposerDraft(surface: string, scope: string): void {
  const key = storageKey(surface, scope);
  const file = readDraftFile(key);
  if (!(scope in file.scopes)) {
    return;
  }
  delete file.scopes[scope];
  writeDraftFile(key, file);
}
