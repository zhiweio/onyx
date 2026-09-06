#!/usr/bin/env python3
"""Export markdown under outputs/markdown to DOCX or PDF.

Prefers LibreOffice writer when present. Falls back to telling the caller
to use the Craft export API.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def _convert_with_soffice(source: Path, out_dir: Path, fmt: str) -> Path:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice is None:
        raise RuntimeError("LibreOffice writer is not installed")
    subprocess.run(
        [soffice, "--headless", "--convert-to", fmt, "--outdir", str(out_dir), str(source)],
        check=True,
        capture_output=True,
        text=True,
    )
    converted = out_dir / f"{source.stem}.{fmt}"
    if not converted.exists():
        raise RuntimeError(f"soffice did not write {converted}")
    return converted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export a markdown report")
    parser.add_argument("source")
    parser.add_argument("--format", choices=("docx", "pdf"), default="pdf")
    parser.add_argument("--out-dir", default="outputs/markdown")
    args = parser.parse_args(argv)
    source = Path(args.source)
    if not source.is_file():
        print(f"missing source: {source}", file=sys.stderr)
        return 1
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        written = _convert_with_soffice(source, out_dir, args.format)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(written)
    return 0


if __name__ == "__main__":
    sys.exit(main())
