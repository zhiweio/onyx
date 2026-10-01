"""Compatibility entry point for the shared, read-only source reviewer."""

import sys
from pathlib import Path

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parents[1] / "original/resources/assets/shared-scripts"
    ),
)
from recipe_style_review import main  # noqa: E402 - needs the sys.path setup above

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
