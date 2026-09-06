"""Fill DOCX {{placeholder}} tokens from JSON data.

Scalar tokens: ``{{entity_name}}`` → a string.

Repeating table rows: a row that contains ``{{findings.title}}`` is a
prototype. The JSON value for ``findings`` is an array of objects; the
row is cloned once per item.

After fill, leftover ``{{...}}`` tokens fail the run. Unused JSON keys
are reported but are not fatal.

Example:
    python .opencode/skills/docx/scripts/fill_template.py \\
      --template template.docx --data data.json --output outputs/filled.docx
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

from docx import Document
from docx.document import Document as DocumentObject
from docx.table import Table, _Cell, _Row
from docx.text.paragraph import Paragraph

_TOKEN_PATTERN = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")


def token_key(name: str) -> str:
    return f"{{{{{name}}}}}"


def load_data(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("data JSON must be an object")
    normalized: dict[str, Any] = {}
    for key, value in data.items():
        if not isinstance(key, str):
            raise ValueError("all data JSON keys must be strings")
        name = key[2:-2].strip() if key.startswith("{{") and key.endswith("}}") else key
        normalized[name] = value
    return normalized


def scalar_mapping(data: dict[str, Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for key, value in data.items():
        if isinstance(value, list):
            continue
        mapping[token_key(key)] = "" if value is None else str(value)
    return mapping


def replace_in_paragraph(paragraph: Paragraph, mapping: dict[str, str]) -> int:
    runs = paragraph.runs
    if not runs:
        return 0

    replacements = 0
    while True:
        full_text = "".join(run.text for run in runs)
        match = next(
            (
                (full_text.find(token), token, replacement)
                for token, replacement in mapping.items()
                if full_text.find(token) != -1
            ),
            None,
        )
        if match is None:
            return replacements

        start, token, replacement = match
        end = start + len(token)
        replace_span(runs, start, end, replacement)
        replacements += 1


def replace_span(runs: Any, start: int, end: int, replacement: str) -> None:
    positions: list[tuple[int, int]] = []
    for run_index, run in enumerate(runs):
        positions.extend(
            (run_index, char_index) for char_index, _ in enumerate(run.text)
        )

    if start >= len(positions) or end <= start:
        raise ValueError("invalid replacement span")

    start_run_index, start_char_index = positions[start]
    end_run_index, end_char_index = positions[end - 1]

    if start_run_index == end_run_index:
        run = runs[start_run_index]
        run.text = (
            run.text[:start_char_index] + replacement + run.text[end_char_index + 1 :]
        )
        return

    start_run = runs[start_run_index]
    end_run = runs[end_run_index]
    start_run.text = start_run.text[:start_char_index] + replacement
    for run_index in range(start_run_index + 1, end_run_index):
        runs[run_index].text = ""
    end_run.text = end_run.text[end_char_index + 1 :]


def iter_table_paragraphs(table: Table) -> list[Paragraph]:
    paragraphs: list[Paragraph] = []
    for row in table.rows:
        paragraphs.extend(iter_row_paragraphs(row))
    return paragraphs


def iter_row_paragraphs(row: _Row) -> list[Paragraph]:
    paragraphs: list[Paragraph] = []
    for cell in row.cells:
        paragraphs.extend(iter_cell_paragraphs(cell))
    return paragraphs


def iter_cell_paragraphs(cell: _Cell) -> list[Paragraph]:
    paragraphs = list(cell.paragraphs)
    for table in cell.tables:
        paragraphs.extend(iter_table_paragraphs(table))
    return paragraphs


def all_paragraphs(document: DocumentObject) -> list[Paragraph]:
    paragraphs = list(document.paragraphs)
    for table in document.tables:
        paragraphs.extend(iter_table_paragraphs(table))
    for section in document.sections:
        paragraphs.extend(section.header.paragraphs)
        paragraphs.extend(section.footer.paragraphs)
        for table in section.header.tables:
            paragraphs.extend(iter_table_paragraphs(table))
        for table in section.footer.tables:
            paragraphs.extend(iter_table_paragraphs(table))
    return paragraphs


def row_text(row: _Row) -> str:
    return "".join(paragraph.text for paragraph in iter_row_paragraphs(row))


def prototype_collection(row: _Row, data: dict[str, Any]) -> str | None:
    """Return the collection name if this row is a repeating prototype."""
    names = _TOKEN_PATTERN.findall(row_text(row))
    collections = {name.split(".", 1)[0] for name in names if "." in name}
    if len(collections) != 1:
        return None
    collection = next(iter(collections))
    value = data.get(collection)
    if not isinstance(value, list):
        return None
    return collection


def expand_prototype_rows(document: DocumentObject, data: dict[str, Any]) -> int:
    """Clone each prototype row once per array item. Returns clones added."""
    clones = 0
    tables = list(document.tables)
    for section in document.sections:
        tables.extend(section.header.tables)
        tables.extend(section.footer.tables)

    for table in tables:
        # Snapshot rows first — cloning mutates the table.
        indexed = list(enumerate(table.rows))
        # Process from the bottom so inserts do not shift later indexes.
        for _, row in reversed(indexed):
            collection = prototype_collection(row, data)
            if collection is None:
                continue
            items = data[collection]
            if not isinstance(items, list) or len(items) <= 1:
                continue
            insert_after = row._tr
            for _ in items[1:]:
                new_tr = deepcopy(row._tr)
                insert_after.addnext(new_tr)
                insert_after = new_tr
                clones += 1
    return clones


def fill_collection_rows(document: DocumentObject, data: dict[str, Any]) -> int:
    """Fill ``{{collection.field}}`` tokens from array items, in row order."""
    replacements = 0
    tables = list(document.tables)
    for section in document.sections:
        tables.extend(section.header.tables)
        tables.extend(section.footer.tables)

    cursors: dict[str, int] = {}
    for table in tables:
        for row in table.rows:
            collection = prototype_collection(row, data)
            if collection is None:
                continue
            items = data[collection]
            if not isinstance(items, list) or not items:
                # Empty list: clear the prototype tokens rather than leave them.
                mapping = {
                    token_key(name): ""
                    for name in _TOKEN_PATTERN.findall(row_text(row))
                    if name.startswith(f"{collection}.")
                }
                for paragraph in iter_row_paragraphs(row):
                    replacements += replace_in_paragraph(paragraph, mapping)
                continue
            index = cursors.get(collection, 0)
            if index >= len(items):
                continue
            item = items[index]
            cursors[collection] = index + 1
            if not isinstance(item, dict):
                raise ValueError(f"each '{collection}' item must be an object")
            mapping = {
                token_key(f"{collection}.{field}"): (
                    "" if value is None else str(value)
                )
                for field, value in item.items()
                if isinstance(field, str)
            }
            for paragraph in iter_row_paragraphs(row):
                replacements += replace_in_paragraph(paragraph, mapping)
    return replacements


def leftover_tokens(document: DocumentObject) -> list[str]:
    found: list[str] = []
    for paragraph in all_paragraphs(document):
        found.extend(_TOKEN_PATTERN.findall(paragraph.text))
    return sorted(set(name.strip() for name in found if name.strip()))


def unused_data_keys(data: dict[str, Any], declared_tokens: list[str]) -> list[str]:
    """JSON keys that do not match any token that was in the template."""
    declared = set(declared_tokens)
    unused: list[str] = []
    for key in data:
        if key in declared:
            continue
        prefix = f"{key}."
        if any(token == key or token.startswith(prefix) for token in declared):
            continue
        unused.append(key)
    return unused


def fill_document(document: DocumentObject, data: dict[str, Any]) -> dict[str, Any]:
    declared_tokens = leftover_tokens(document)
    clones = expand_prototype_rows(document, data)
    table_replacements = fill_collection_rows(document, data)
    scalar_replacements = 0
    mapping = scalar_mapping(data)
    for paragraph in all_paragraphs(document):
        scalar_replacements += replace_in_paragraph(paragraph, mapping)

    leftover = leftover_tokens(document)
    return {
        "replacements": scalar_replacements + table_replacements,
        "row_clones": clones,
        "leftover": leftover,
        "unused_keys": unused_data_keys(data, declared_tokens),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fill {{placeholder}} tokens in a DOCX template"
    )
    parser.add_argument("--template", required=True, help="Input .docx template")
    parser.add_argument(
        "--data", required=True, help="JSON object with placeholder values"
    )
    parser.add_argument("--output", required=True, help="Output .docx path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    template_path = Path(args.template)
    data_path = Path(args.data)
    output_path = Path(args.output)

    if not template_path.is_file():
        raise FileNotFoundError(f"template not found: {template_path}")
    if template_path.suffix.lower() != ".docx":
        raise ValueError("template must be a .docx file")
    if not data_path.is_file():
        raise FileNotFoundError(f"data file not found: {data_path}")

    data = load_data(data_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document = Document(str(template_path))
    result = fill_document(document, data)
    leftover = result["leftover"]
    if leftover:
        raise ValueError(
            "unfilled placeholders remain: " + ", ".join(f"{{{{{n}}}}}" for n in leftover)
        )
    document.save(str(output_path))
    print(
        json.dumps(
            {
                "output": str(output_path),
                "replacements": result["replacements"],
                "row_clones": result["row_clones"],
                "unused_keys": result["unused_keys"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
