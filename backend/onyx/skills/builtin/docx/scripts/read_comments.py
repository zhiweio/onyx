"""Extract comments and tracked changes from a DOCX file as JSON.

Example:
    python .opencode/skills/docx/scripts/read_comments.py --input reviewed.docx --output outputs/review.json
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

import defusedxml.ElementTree as ET

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": WORD_NS}


def qname(local_name: str) -> str:
    return f"{{{WORD_NS}}}{local_name}"


def text_from_element(element: ET.Element) -> str:
    parts: list[str] = []
    for node in element.iter():
        if node.tag in {qname("t"), qname("delText")} and node.text:
            parts.append(node.text)
        elif node.tag == qname("tab"):
            parts.append("\t")
        elif node.tag in {qname("br"), qname("cr")}:
            parts.append("\n")
    return "".join(parts)


def parse_comments(archive: zipfile.ZipFile) -> list[dict[str, str | None]]:
    if "word/comments.xml" not in archive.namelist():
        return []

    root = ET.fromstring(archive.read("word/comments.xml"))
    return [
        {
            "id": comment.get(qname("id")),
            "author": comment.get(qname("author")),
            "initials": comment.get(qname("initials")),
            "date": comment.get(qname("date")),
            "text": text_from_element(comment),
        }
        for comment in root.findall("w:comment", NS)
    ]


def parse_tracked_changes(archive: zipfile.ZipFile) -> list[dict[str, str | None]]:
    if "word/document.xml" not in archive.namelist():
        raise ValueError(
            "word/document.xml not found; input is not a valid DOCX package"
        )

    root = ET.fromstring(archive.read("word/document.xml"))
    changes: list[dict[str, str | None]] = []
    for kind in ("ins", "del"):
        changes.extend(
            {
                "type": "insertion" if kind == "ins" else "deletion",
                "id": element.get(qname("id")),
                "author": element.get(qname("author")),
                "date": element.get(qname("date")),
                "text": text_from_element(element),
            }
            for element in root.findall(f".//w:{kind}", NS)
        )
    return changes


def extract_review_data(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"input not found: {path}")
    if path.suffix.lower() != ".docx":
        raise ValueError("input must be a .docx file")

    with zipfile.ZipFile(path) as archive:
        return {
            "input": str(path),
            "comments": parse_comments(archive),
            "tracked_changes": parse_tracked_changes(archive),
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract DOCX comments and tracked changes as JSON"
    )
    parser.add_argument("--input", required=True, help="Input .docx file")
    parser.add_argument("--output", help="Optional JSON output path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = extract_review_data(Path(args.input))
    content = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content + "\n", encoding="utf-8")
    else:
        print(content)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, zipfile.BadZipFile, ET.ParseError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
