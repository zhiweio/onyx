"""Deterministic summary of an MCP tool result.

Stored with the blob as ops metadata. The model receives the original tool
result, not this digest. Built by structural projection so the same body
always produces the same summary.
"""

import json
from typing import Any

from onyx.mcp_gateway.models import CachePolicySpec

# Enough of a text block to recognize the content and decide whether to read on.
_TEXT_PREVIEW_CHARS = 600
# Keys are cheap and the most useful part of the summary, but an object with
# thousands of them is itself a payload.
_MAX_KEYS = 40
_MAX_SAMPLE_ITEMS = 3
_MAX_DEPTH = 4


def _describe(node: Any, depth: int = 0) -> Any:
    """Shape of a value: types, sizes, and keys, but not the data itself."""
    if depth >= _MAX_DEPTH:
        return {"type": type(node).__name__, "truncated": True}

    if isinstance(node, dict):
        keys = list(node.keys())
        described: dict[str, Any] = {
            "type": "object",
            "key_count": len(keys),
            "keys": [str(key) for key in keys[:_MAX_KEYS]],
        }
        if len(keys) > _MAX_KEYS:
            described["keys_truncated"] = True
        described["fields"] = {
            str(key): _describe(node[key], depth + 1) for key in keys[:_MAX_KEYS]
        }
        return described

    if isinstance(node, list):
        described = {"type": "array", "length": len(node)}
        if node:
            described["item_shape"] = _describe(node[0], depth + 1)
        return described

    if isinstance(node, str):
        if len(node) <= _TEXT_PREVIEW_CHARS:
            return {"type": "string", "length": len(node), "value": node}
        return {
            "type": "string",
            "length": len(node),
            "preview": node[:_TEXT_PREVIEW_CHARS],
            "truncated": True,
        }

    if node is None:
        return {"type": "null"}
    return {"type": type(node).__name__, "value": node}


def extract_path(payload: Any, path: str) -> Any:
    """Read a dotted path, with numeric segments indexing into arrays.

    Returns None for a path that does not resolve, so a pack can name fields
    that only some tools return without special-casing each one.
    """
    node = payload
    for segment in path.split("."):
        if isinstance(node, dict):
            if segment not in node:
                return None
            node = node[segment]
        elif isinstance(node, list):
            if not segment.lstrip("-").isdigit():
                return None
            index = int(segment)
            if index >= len(node) or index < -len(node):
                return None
            node = node[index]
        else:
            return None
    return node


def _content_summary(payload: dict[str, Any]) -> dict[str, Any]:
    """Per-block view of the MCP `content` array."""
    blocks = payload.get("content")
    if not isinstance(blocks, list):
        return {"block_count": 0, "blocks": []}

    described: list[dict[str, Any]] = []
    total_text = 0
    for block in blocks:
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("type") or "unknown")
        entry: dict[str, Any] = {"type": block_type}
        if block_type == "text":
            text = str(block.get("text") or "")
            total_text += len(text)
            entry["length"] = len(text)
            entry["preview"] = text[:_TEXT_PREVIEW_CHARS]
            if len(text) > _TEXT_PREVIEW_CHARS:
                entry["truncated"] = True
        elif block_type == "image":
            entry["mime_type"] = block.get("mimeType")
        described.append(entry)
        if len(described) >= _MAX_SAMPLE_ITEMS:
            break

    return {
        "block_count": len(blocks),
        "total_text_chars": total_text,
        "blocks": described,
    }


def _shrink(digest: dict[str, Any], max_bytes: int) -> dict[str, Any]:
    """Drop the most verbose sections until the digest fits the budget.

    Order matters: the structural map of `structuredContent` is the first thing
    to go, then text previews, then the field map. What survives is always
    enough to name the tool's output.
    """
    if len(json.dumps(digest, ensure_ascii=False).encode("utf-8")) <= max_bytes:
        return digest

    trimmed = dict(digest)
    for section in ("structured_shape", "content", "extracted"):
        trimmed.pop(section, None)
        trimmed["digest_truncated"] = True
        if len(json.dumps(trimmed, ensure_ascii=False).encode("utf-8")) <= max_bytes:
            return trimmed

    # Nothing left to drop: keep only the counters.
    return {
        "is_error": trimmed.get("is_error", False),
        "digest_truncated": True,
    }


def build_digest(
    payload: dict[str, Any],
    policy: CachePolicySpec,
    *,
    size_bytes: int,
) -> dict[str, Any]:
    """Summarize one MCP `CallToolResult` payload."""
    digest: dict[str, Any] = {
        "is_error": bool(payload.get("isError")),
        "total_bytes": size_bytes,
        "content": _content_summary(payload),
    }

    structured = payload.get("structuredContent")
    if structured is not None:
        digest["structured_shape"] = _describe(structured)

    if policy.digest_paths:
        extracted = {
            path: value
            for path in policy.digest_paths
            if (value := extract_path(payload, path)) is not None
        }
        if extracted:
            digest["extracted"] = extracted

    return _shrink(digest, policy.digest_max_bytes)
