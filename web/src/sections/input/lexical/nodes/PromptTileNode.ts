import {
  $applyNodeReplacement,
  DecoratorNode,
  type LexicalNode,
  type NodeKey,
  type RangeSelection,
  type SerializedLexicalNode,
} from "lexical";
import {
  createRichInputTileNode,
  getPasteTileMeta,
  getPasteTilePreview,
} from "@/lib/richInputTile";

/**
 * PromptTileNode — an atomic inline "paste tile": a chip that carries a long
 * pasted text collapsed (preview + line/char count), rendered through the
 * shared `createRichInputTileNode` DOM so the existing tile CSS, the popover,
 * and the e2e contract ([data-rich-tile], data-text, preview/meta spans)
 * all keep working on the Lexical editor.
 *
 * The full text is the canonical output: serialization submits it, the
 * popover edits it, and re-pasting the same text expands the tile.
 */

interface SerializedPromptTileNode extends SerializedLexicalNode {
  text: string;
}

export class PromptTileNode extends DecoratorNode<null> {
  __text: string;

  static getType(): string {
    return "prompt-tile";
  }

  static clone(node: PromptTileNode): PromptTileNode {
    return new PromptTileNode(node.__text, node.__key);
  }

  static importJSON(serializedNode: SerializedPromptTileNode): PromptTileNode {
    return $createPromptTileNode(serializedNode.text);
  }

  constructor(text: string, key?: NodeKey) {
    super(key);
    this.__text = text;
  }

  exportJSON(): SerializedPromptTileNode {
    return {
      ...super.exportJSON(),
      type: "prompt-tile",
      version: 1,
      text: this.__text,
    };
  }

  createDOM(): HTMLElement {
    const dom = createRichInputTileNode({
      type: "paste",
      text: this.__text,
      preview: getPasteTilePreview(this.__text),
      meta: getPasteTileMeta(this.__text),
    });
    // Map the DOM back to the node key so click handlers can resolve it.
    dom.setAttribute("data-tile-node-key", this.__key);
    return dom;
  }

  updateDOM(prevNode: PromptTileNode): boolean {
    // Text edits swap the node wholesale; a changed text forces a DOM rebuild.
    return prevNode.__text !== this.__text;
  }

  isInline(): boolean {
    return true;
  }

  isKeyboardSelectable(): boolean {
    return true;
  }

  decorate(): null {
    return null;
  }

  /** Canonical full text (submission + clipboard serialization). */
  getText(): string {
    return this.getLatest().__text;
  }
}

export function $createPromptTileNode(text: string): PromptTileNode {
  return $applyNodeReplacement(new PromptTileNode(text));
}

export function $isPromptTileNode(
  node: LexicalNode | null | undefined,
): node is PromptTileNode {
  return node instanceof PromptTileNode;
}

/**
 * Whether the selection covers exactly this tile. A decorator node has no
 * child points, so a covering range uses element points on the parent at the
 * tile's child index — this is the tile "highlight" state.
 */
export function selectionCoversExactly(
  selection: RangeSelection,
  node: PromptTileNode,
): boolean {
  const points = selection.getStartEndPoints();
  if (!points) {
    return false;
  }
  const [start, end] = points;
  const parent = node.getParent();
  if (parent === null) {
    return false;
  }
  const index = node.getIndexWithinParent();
  const parentKey = parent.getKey();
  return (
    start.type === "element" &&
    start.key === parentKey &&
    start.offset === index &&
    end.type === "element" &&
    end.key === parentKey &&
    end.offset === index + 1
  );
}
