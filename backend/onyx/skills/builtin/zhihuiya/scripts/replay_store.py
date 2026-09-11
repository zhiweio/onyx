"""Persist Zhihuiya MCP results as replayable evidence.

Key = md5(tool + canonical JSON arguments). Truncated seeds must be refetched
before a report cites them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TRUNCATED_TAG = "TRUNCATED-SEED"


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def cache_key(tool: str, arguments: dict[str, Any]) -> str:
    payload = f"{tool}\n{canonical_json(arguments)}"
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


def store_root(report_id: str, base: Path | None = None) -> Path:
    root = base or Path("outputs/mcp/zhihuiya/stores")
    return root / report_id


def is_truncated(body: Any) -> bool:
    if isinstance(body, str) and TRUNCATED_TAG in body:
        return True
    if isinstance(body, dict):
        text = json.dumps(body, ensure_ascii=False)
        return TRUNCATED_TAG in text or body.get("truncated") is True
    return False


def write_capture(
    report_id: str,
    tool: str,
    arguments: dict[str, Any],
    body: Any,
    *,
    base: Path | None = None,
) -> Path:
    root = store_root(report_id, base)
    captures = root / "captures"
    captures.mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(exist_ok=True)
    (root / "digest").mkdir(exist_ok=True)
    key = cache_key(tool, arguments)
    path = captures / f"{key}.json"
    record = {
        "tool": tool,
        "arguments": arguments,
        "key": key,
        "truncated": is_truncated(body),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "body": body,
    }
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    _refresh_manifest(root)
    return path


def read_capture(
    report_id: str,
    tool: str,
    arguments: dict[str, Any],
    *,
    base: Path | None = None,
) -> dict[str, Any] | None:
    path = store_root(report_id, base) / "captures" / f"{cache_key(tool, arguments)}.json"
    if not path.is_file():
        return None
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else None


def _refresh_manifest(root: Path) -> None:
    captures = sorted((root / "captures").glob("*.json"))
    items: list[dict[str, Any]] = []
    truncated = 0
    for path in captures:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if loaded.get("truncated"):
            truncated += 1
        items.append(
            {
                "key": loaded.get("key"),
                "tool": loaded.get("tool"),
                "truncated": loaded.get("truncated", False),
                "file": str(path.relative_to(root)),
            }
        )
    manifest = {
        "count": len(items),
        "truncated": truncated,
        "items": items,
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    readme = root / "README.md"
    if not readme.is_file():
        readme.write_text(
            "# Zhihuiya replay store\n\n"
            "Cite only captures listed in `manifest.json`. "
            f"Refetch any row tagged `{TRUNCATED_TAG}`.\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Zhihuiya replay store")
    parser.add_argument("action", choices=("key", "write", "read"))
    parser.add_argument("--report-id", required=True)
    parser.add_argument("--tool", required=True)
    parser.add_argument("--args", default="{}")
    parser.add_argument("--body-file")
    parser.add_argument("--base")
    parsed = parser.parse_args()
    arguments = json.loads(parsed.args)
    base = Path(parsed.base) if parsed.base else None
    if parsed.action == "key":
        print(cache_key(parsed.tool, arguments))
        return
    if parsed.action == "write":
        if not parsed.body_file:
            raise SystemExit("--body-file is required for write")
        body = json.loads(Path(parsed.body_file).read_text(encoding="utf-8"))
        path = write_capture(
            parsed.report_id, parsed.tool, arguments, body, base=base
        )
        print(path)
        return
    record = read_capture(parsed.report_id, parsed.tool, arguments, base=base)
    if record is None:
        raise SystemExit("capture not found")
    print(json.dumps(record, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
