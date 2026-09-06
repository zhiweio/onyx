"""Recalculate an XLSX workbook with LibreOffice so formula caches are current.

openpyxl stores formulas but never evaluates them, so a workbook it wrote has no
usable cached results. Run this before reading values with ``data_only=True``.

Example:
    python .opencode/skills/xlsx/scripts/recalculate.py --input model.xlsx --output outputs/model-recalculated.xlsx
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SUPPORTED_SUFFIXES = frozenset({".xlsx", ".xlsm", ".ods"})
CONVERSION_TIMEOUT_SECONDS = 300


def recalculate(input_path: Path, output_path: Path) -> None:
    if not input_path.is_file():
        raise FileNotFoundError(f"input not found: {input_path}")
    if input_path.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError("input must be an .xlsx, .xlsm, or .ods workbook")

    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice is None:
        raise RuntimeError(
            "LibreOffice is not available; install it or open the workbook in a "
            "spreadsheet application to refresh cached values"
        )

    target_format = (output_path.suffix.lstrip(".") or "xlsx").lower()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert into a scratch directory: LibreOffice names the result after the
    # input stem, which need not match the requested output name.
    with tempfile.TemporaryDirectory(prefix="xlsx-recalculate-") as scratch:
        scratch_dir = Path(scratch)
        result = subprocess.run(
            [
                soffice,
                "--headless",
                "--convert-to",
                target_format,
                "--outdir",
                str(scratch_dir),
                str(input_path),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=CONVERSION_TIMEOUT_SECONDS,
        )
        if result.returncode != 0:
            raise RuntimeError(
                result.stderr.strip() or result.stdout.strip() or "LibreOffice failed"
            )

        produced = next(iter(scratch_dir.glob(f"*.{target_format}")), None)
        if produced is None:
            raise RuntimeError("LibreOffice did not create the recalculated workbook")
        shutil.move(str(produced), str(output_path))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Recalculate workbook formulas with LibreOffice"
    )
    parser.add_argument("--input", required=True, help="Input workbook")
    parser.add_argument("--output", required=True, help="Output workbook")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path = Path(args.output)
    recalculate(Path(args.input), output_path)
    print(f"Recalculated workbook written to {output_path}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
