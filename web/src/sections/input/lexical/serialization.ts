import { $getRoot, $isElementNode, type LexicalNode } from "lexical";
import { $isPromptMentionNode } from "@/sections/input/lexical/nodes/PromptMentionNode";

/**
 * Serialize the editor tree to prompt markdown: mention chips contribute
 * their canonical markdown, everything else its text content. Blocks are
 * joined with "\n\n" to mirror how Lexical splits paragraphs.
 */
export function $getPromptMarkdown(node: LexicalNode = $getRoot()): string {
  if ($isPromptMentionNode(node)) return node.getMarkdown();
  if (!$isElementNode(node)) return node.getTextContent();
  const children = node.getChildren();
  return children
    .map(
      (child, index) =>
        $getPromptMarkdown(child) +
        ($isElementNode(child) &&
        !child.isInline() &&
        index < children.length - 1
          ? "\n\n"
          : ""),
    )
    .join("");
}
