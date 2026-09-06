"""Fill AcroForm fields in a PDF from JSON data.

Example:
    python .opencode/skills/pdf/scripts/fill_form.py --input form.pdf --data fields.json --output outputs/filled.pdf
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pypdf import PdfReader, PdfWriter


def load_fields(path: Path) -> dict[str, str]:
    data: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("data JSON must be an object")
    fields: dict[str, str] = {}
    for key, value in data.items():
        if not isinstance(key, str):
            raise ValueError("all field names must be strings")
        fields[key] = "" if value is None else str(value)
    return fields


def fill_form(
    input_path: Path, data_path: Path, output_path: Path
) -> dict[str, object]:
    if not input_path.is_file():
        raise FileNotFoundError(f"input not found: {input_path}")
    if not data_path.is_file():
        raise FileNotFoundError(f"data file not found: {data_path}")

    fields = load_fields(data_path)
    existing_fields = PdfReader(str(input_path)).get_fields() or {}
    missing = sorted(set(fields) - set(existing_fields))
    if missing:
        raise ValueError(f"field not found in PDF: {missing[0]}")

    # clone_from copies the AcroForm together with the pages, so /Fields keeps
    # pointing at the widgets being written. Rebuilding the root by hand leaves
    # stale references and silently drops values.
    writer = PdfWriter(clone_from=str(input_path))
    # Without NeedAppearances many viewers render an empty widget even though
    # the value is stored.
    writer.set_need_appearances_writer(True)
    # None targets every page. Passing writer.pages would hand pypdf a virtual
    # list it does not treat as a page selection, and the write silently no-ops.
    writer.update_page_form_field_values(None, fields)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as output_file:
        writer.write(output_file)

    # Read the result back: a write that did not take is otherwise invisible.
    verify_fields = PdfReader(str(output_path)).get_fields() or {}
    written = {
        name: verify_fields[name].get("/V") for name in fields if name in verify_fields
    }
    unwritten = sorted(set(fields) - set(written))
    if unwritten:
        raise ValueError(f"field did not persist: {unwritten[0]}")
    return {"output": str(output_path), "fields_written": written}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fill PDF AcroForm fields from JSON")
    parser.add_argument("--input", required=True, help="Input PDF form")
    parser.add_argument("--data", required=True, help="JSON object with field values")
    parser.add_argument("--output", required=True, help="Output PDF")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = fill_form(Path(args.input), Path(args.data), Path(args.output))
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
