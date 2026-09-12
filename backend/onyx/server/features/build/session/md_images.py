"""Resolve and size local images referenced from Craft Markdown.

Markdown in the sandbox often points at sibling files
(``figures/plot.png``) or ``sandbox://outputs/...`` URIs. Preview and
export both need a workspace-relative path that stays inside the session
root.
"""

from __future__ import annotations

from collections.abc import Callable
from io import BytesIO
from pathlib import PurePosixPath
from urllib.parse import unquote

from PIL import Image as PILImage
from PIL import UnidentifiedImageError

from onyx.server.features.build.session.md_document import Node

ImageLoader = Callable[[str], bytes | None]

_SANDBOX_SCHEME = "sandbox:"
_REMOTE_SCHEMES = ("http:", "https:", "mailto:", "data:", "blob:")
_WORKSPACE_ROOTS = (
    "outputs/",
    "attachments/",
    "project/",
    "uploads/",
    "user_library/",
)
_EMBED_FORMATS = frozenset({"PNG", "JPEG", "GIF"})
_ASSUMED_DPI = 96.0
_MAX_WIDTH_IN = 6.0
_MAX_HEIGHT_IN = 8.0


def resolve_local_markdown_image_path(src: str, markdown_path: str) -> str | None:
    """Return a workspace-relative path for a local Markdown image URL.

    Remote, data, and other non-sandbox schemes return None. ``..`` that
    would leave the workspace also returns None.
    """
    raw = _decode_src(src)
    if not raw:
        return None

    scheme_end = _scheme_prefix_end(raw)
    if scheme_end is not None:
        scheme = raw[:scheme_end].lower()
        if scheme != _SANDBOX_SCHEME:
            return None
        raw = raw[scheme_end:].lstrip("/")

    raw = raw.split("#", 1)[0].split("?", 1)[0]
    raw = raw.replace("\\", "/").strip()
    if not raw:
        return None

    if raw.startswith("/"):
        raw = raw.lstrip("/")

    if _is_workspace_root_path(raw):
        return _normalize_workspace_parts(raw.split("/"), base_parts=())

    markdown_dir = _markdown_dir(markdown_path)
    return _normalize_workspace_parts(raw.split("/"), base_parts=markdown_dir)


def attach_image_bytes(nodes: list[Node], image_loader: ImageLoader | None) -> None:
    """Load local image bytes onto each image node that the loader can resolve."""
    if image_loader is None:
        return
    for node in nodes:
        if node.get("type") == "image":
            src = str((node.get("attrs") or {}).get("url") or "")
            if src:
                data = _safe_load(image_loader, src)
                if data:
                    node["image_bytes"] = data
        children = node.get("children")
        if isinstance(children, list):
            attach_image_bytes(children, image_loader)


def image_bytes(node: Node) -> bytes | None:
    data = node.get("image_bytes")
    if isinstance(data, (bytes, bytearray)) and data:
        return bytes(data)
    return None


def is_embeddable_image_bytes(data: bytes) -> bool:
    return fit_image_display_size(data) is not None


def fit_image_display_size(
    data: bytes,
    *,
    max_width_in: float = _MAX_WIDTH_IN,
    max_height_in: float = _MAX_HEIGHT_IN,
) -> tuple[float, float] | None:
    """Return display size in inches, or None if the bytes are not embeddable."""
    try:
        with PILImage.open(BytesIO(data)) as image:
            if image.format not in _EMBED_FORMATS:
                return None
            width_px, height_px = image.size
    except (OSError, UnidentifiedImageError, ValueError):
        return None
    if width_px <= 0 or height_px <= 0:
        return None
    width_in = width_px / _ASSUMED_DPI
    height_in = height_px / _ASSUMED_DPI
    scale = min(max_width_in / width_in, max_height_in / height_in, 1.0)
    return width_in * scale, height_in * scale


def _safe_load(image_loader: ImageLoader, src: str) -> bytes | None:
    try:
        data = image_loader(src)
    except Exception:
        return None
    if not data or not is_embeddable_image_bytes(data):
        return None
    return data


def _decode_src(src: str) -> str:
    text = (src or "").strip()
    if not text:
        return ""
    try:
        return unquote(text)
    except ValueError:
        return text


def _scheme_prefix_end(src: str) -> int | None:
    for index, char in enumerate(src):
        if char == ":":
            return index + 1 if index > 0 else None
        if not (char.isalnum() or char in "+.-"):
            return None
    return None


def _is_workspace_root_path(path: str) -> bool:
    lowered = path.lower()
    return any(lowered.startswith(root) for root in _WORKSPACE_ROOTS)


def _markdown_dir(markdown_path: str) -> tuple[str, ...]:
    cleaned = (markdown_path or "").replace("\\", "/").strip().lstrip("/")
    parent = PurePosixPath(cleaned).parent
    if parent.as_posix() in (".", ""):
        return ()
    return tuple(part for part in parent.parts if part not in (".", ""))


def _normalize_workspace_parts(
    parts: list[str],
    *,
    base_parts: tuple[str, ...],
) -> str | None:
    stack = [part for part in base_parts if part and part != "."]
    for part in parts:
        if not part or part == ".":
            continue
        if part == "..":
            if not stack:
                return None
            stack.pop()
            continue
        if "/" in part or "\\" in part or "\x00" in part:
            return None
        stack.append(part)
    if not stack:
        return None
    return "/".join(stack)
