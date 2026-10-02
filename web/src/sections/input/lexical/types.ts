import type { EditorState } from "lexical";
import type { PickerEntry, PickerSections } from "@/lib/skills/picker";

/**
 * Shared types for the Lexical prompt-input kernel
 * (`web/src/sections/input/lexical/`).
 *
 * The kernel is a three-layer composer: the core editor + shell (always
 * present), optional plugins (slash/mention menus, prompt history, drafts),
 * and slots (top content + toolbar) filled by the integrating surface
 * (craft full form, /app light form).
 */

export type ComposerMentionCategory =
  | "files"
  | "skills"
  | "commands"
  | "apps"
  | "mcp";

export interface ComposerMentionData {
  /** Library file id or sandbox path reference. */
  fileId?: string | number;
  path?: string;
  /** Where the entry came from; surfaces may scope search by it. */
  scope?: "library" | "sandbox" | "builtin" | "user";
}

/** An atomic chip inserted into the editor. `markdown` is what the chip
 * serializes to when the prompt is submitted or copied. */
export interface ComposerMention {
  id: string;
  category: ComposerMentionCategory;
  label: string;
  value: string;
  markdown: string;
  description?: string;
  data?: ComposerMentionData;
}

/** Imperative handle over the Lexical editor, replacing `BaseInputBarHandle`. */
export interface LexicalPromptInputHandle {
  clear(): void;
  focus(): void;
  /** Serialized prompt (mention chips become their markdown). */
  getText(): string;
  setText(text: string): void;
  appendText(text: string): void;
  /** Insert a chip at the caret (end of editor when no selection). */
  insertMention(mention: ComposerMention): void;
  /** All chips currently in the editor, in document order. */
  getMentions(): ComposerMention[];
  /** Remove the chip with the given id. Returns true when one was removed. */
  removeMention(id: string): boolean;
  getEditorStateJson(): string;
  /** Restores a persisted editor state; falls back to plain text when the
   * JSON cannot be parsed. Returns false when neither could be applied. */
  setEditorStateJson(editorStateJson: string): boolean;
}

export type LexicalSubmitResult = boolean | void;

export interface LexicalPasteEvent {
  clipboardData: DataTransfer | null;
  preventDefault(): void;
  stopPropagation?(): void;
}

export interface TriggerMenuConfig {
  id: string;
  /** Characters that open this menu when typed at a word start. */
  triggerChars: readonly string[];
  /** Entry data snapshot; re-rendered as the integrator's data loads. */
  sections: PickerSections;
  /** Open the menu even when no entries exist yet (e.g. "@" with an empty
   * library) so the popover can show its empty state. */
  showWhenEmpty?: boolean;
  /** Overrides the popover's empty-state text for this menu. */
  emptyMessage?: string;
  /**
   * Handle a pick. Return true when the entry is consumed without inserting a
   * chip (e.g. an immediate command such as /compact or a navigation).
   */
  onPick?: (entry: PickerEntry, triggerChar: string) => boolean;
  /** Build the chip inserted for a picked entry (default: label + markdown
   * from the entry). */
  entryToMention?: (entry: PickerEntry, triggerChar: string) => ComposerMention;
}

export interface ComposerDraftSnapshot {
  text: string;
  editorStateJson?: string;
}

export type { EditorState };
