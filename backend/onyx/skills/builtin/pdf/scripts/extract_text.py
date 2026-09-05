"""Extract PDF text by page as plain text or JSON.

Example:
    python .opencode/skills/pdf/scripts/extract_text.py --input report.pdf --pages 1-3,7 --format json --output outputs/text.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pypdf import PdfReader


def parse_pages(spec: str | None, page_count: int) -> list[int]:
    if spec is None or not spec.strip():
        return list(range(page_count))

    pages: list[int] = []
    for part in spec.split(","):
        item = part.strip()
        if not item:
            continue
        if "-" in item:
            start_text, end_text = item.split("-", 1)
            start = int(start_text)
            end = int(end_text)
            if start > end:
                raise ValueError(f"invalid page range: {item}")
            pages.extend(range(start - 1, end))
        else:
            pages.append(int(item) - 1)

    invalid = [page + 1 for page in pages if page < 0 or page >= page_count]
    if invalid:
        raise ValueError(f"page out of range: {invalid[0]}")
    return pages


def extract_text(path: Path, pages_spec: str | None) -> list[dict[str, object]]:
    if not path.is_file():
        raise FileNotFoundError(f"input not found: {path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError("input must be a .pdf file")

    reader = PdfReader(str(path))
    page_indexes = parse_pages(pages_spec, len(reader.pages))
    return [
        {"page": index + 1, "text": reader.pages[index].extract_text() or ""}
        for index in page_indexes
    ]


def format_text(pages: list[dict[str, object]]) -> str:
    return "\n\f\n".join(str(page["text"]) for page in pages)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract text from a PDF")
    parser.add_argument("--input", required=True, help="Input PDF")
    parser.add_argument(
        "--pages", help="Pages to extract, such as 1-3,7. Defaults to all pages"
    )
    parser.add_argument(
        "--format", choices=("text", "json"), default="text", help="Output format"
    )
    parser.add_argument("--output", help="Optional output file")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    pages = extract_text(Path(args.input), args.pages)
    content = (
        json.dumps({"input": args.input, "pages": pages}, indent=2, ensure_ascii=False)
        if args.format == "json"
        else format_text(pages)
    )
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content + "\n", encoding="utf-8")
    else:
        print(content)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
