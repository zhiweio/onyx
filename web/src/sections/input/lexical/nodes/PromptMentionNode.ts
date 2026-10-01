import {
  $applyNodeReplacement,
  type EditorConfig,
  type LexicalNode,
  type NodeKey,
  type SerializedTextNode,
  TextNode,
} from "lexical";
import type {
  ComposerMention,
  ComposerMentionCategory,
  ComposerMentionData,
} from "@/sections/input/lexical/types";

/**
 * Atomic inline chip node for prompt mentions (skills, files, apps, ...).
 * Modeled on ZCode's PromptMentionNode: a TextNode in "token" mode whose
 * canonical `markdown` is only used for submission serialization, while the
 * visible text stays the (short) label.
 */

const CHIP_CLASS_NAME =
  "prompt-mention-chip inline-flex items-baseline rounded-06 bg-background-tint-02 px-1 mx-0.5 font-secondary-action text-text-04";

const CATEGORY_MARK: Record<ComposerMentionCategory, string> = {
  files: "@",
  skills: "/",
  commands: "/",
  apps: "@",
  mcp: "@",
};

export interface PromptMentionPayload extends ComposerMention {}

type SerializedPromptMentionNode = SerializedTextNode & {
  category: ComposerMentionCategory;
  data?: ComposerMentionData;
  description: string;
  markdown: string;
  mentionId: string;
  type: "prompt-mention";
  value: string;
  version: 1;
};

export class PromptMentionNode extends TextNode {
  __category: ComposerMentionCategory;
  __data?: ComposerMentionData;
  __description: string;
  __markdown: string;
  __mentionId: string;
  __value: string;

  static getType(): string {
    return "prompt-mention";
  }

  static clone(node: PromptMentionNode): PromptMentionNode {
    return new PromptMentionNode(
      {
        id: node.__mentionId,
        category: node.__category,
        label: node.__text,
        value: node.__value,
        markdown: node.__markdown,
        description: node.__description,
        data: node.__data,
      },
      node.__key,
    );
  }

  static importJSON(
    serializedNode: SerializedPromptMentionNode,
  ): PromptMentionNode {
    const node = new PromptMentionNode({
      id: serializedNode.mentionId,
      category: serializedNode.category,
      label: serializedNode.text,
      value: serializedNode.value,
      markdown: serializedNode.markdown,
      description: serializedNode.description,
      data: serializedNode.data,
    });
    node.setFormat(serializedNode.format);
    node.setDetail(serializedNode.detail);
    node.setMode(serializedNode.mode);
    node.setStyle(serializedNode.style);
    return node;
  }

  constructor(payload: PromptMentionPayload, key?: NodeKey) {
    super(payload.label, key);
    this.__mentionId = payload.id;
    this.__category = payload.category;
    this.__value = payload.value;
    this.__markdown = payload.markdown;
    this.__description = payload.description ?? "";
    this.__data = payload.data;
  }

  createDOM(config: EditorConfig): HTMLElement {
    const dom = super.createDOM(config);
    dom.className = CHIP_CLASS_NAME;
    dom.setAttribute("data-mention-category", this.__category);
    dom.setAttribute("data-mention-id", this.__mentionId);
    dom.setAttribute("spellcheck", "false");
    return dom;
  }

  updateDOM(
    prevNode: PromptMentionNode,
    dom: HTMLElement,
    config: EditorConfig,
  ): boolean {
    const shouldUpdate = super.updateDOM(prevNode as this, dom, config);
    if (prevNode.__mentionId !== this.__mentionId) {
      dom.setAttribute("data-mention-id", this.__mentionId);
    }
    return shouldUpdate;
  }

  exportJSON(): SerializedPromptMentionNode {
    return {
      ...super.exportJSON(),
      type: "prompt-mention",
      version: 1,
      mentionId: this.__mentionId,
      category: this.__category,
      value: this.__value,
      markdown: this.__markdown,
      description: this.__description,
      data: this.__data,
    };
  }

  /** Editor offsets use the visible label; this is the canonical output. */
  getMarkdown(): string {
    return this.getLatest().__markdown;
  }

  isTextEntity(): true {
    return true;
  }

  canInsertTextBefore(): false {
    return false;
  }

  canInsertTextAfter(): false {
    return false;
  }

  getMention(): PromptMentionPayload {
    return {
      id: this.__mentionId,
      category: this.__category,
      label: this.__text,
      value: this.__value,
      markdown: this.__markdown,
      description: this.__description,
      data: this.__data,
    };
  }
}

export function mentionDisplayLabel(
  category: ComposerMentionCategory,
  label: string,
): string {
  const mark = CATEGORY_MARK[category];
  if (!mark || label.startsWith(mark)) {
    return label;
  }
  return `${mark}${label}`;
}

export function $createPromptMentionNode(
  payload: PromptMentionPayload,
): PromptMentionNode {
  const node = new PromptMentionNode(payload);
  node.setMode("token");
  return $applyNodeReplacement(node);
}

export function $isPromptMentionNode(
  node: LexicalNode | null | undefined,
): node is PromptMentionNode {
  return node instanceof PromptMentionNode;
}
