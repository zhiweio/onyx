#!/usr/bin/env python3
"""Minimal ``rg`` stand-in for Craft sandboxes that lack the ripgrep binary.

OpenCode's skill and grep tools spawn ``rg``. When the binary is missing they
try to download it from GitHub, which the sandbox egress proxy often blocks.
This shim implements the flag subset those tools use so skills can load.
Exit codes match ripgrep: 0 = matches, 1 = no matches, 2 = error.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys
from collections.abc import Iterator
from pathlib import Path


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--no-config", action="store_true")
    parser.add_argument("--version", action="store_true")
    parser.add_argument("--files", action="store_true")
    parser.add_argument("--hidden", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-messages", action="store_true")
    parser.add_argument("--glob", action="append", default=[])
    parser.add_argument("--iglob", action="append", default=[])
    parser.add_argument("--max-count", type=int, default=None)
    parser.add_argument("-i", "--ignore-case", action="store_true")
    parser.add_argument("-n", action="store_true")
    parser.add_argument("-l", "--files-with-matches", action="store_true")
    parser.add_argument("rest", nargs="*")
    return parser.parse_known_args(argv)[0]


def _split_globs(globs: list[str]) -> tuple[list[str], list[str]]:
    include: list[str] = []
    exclude: list[str] = []
    for raw in globs:
        if raw.startswith("!"):
            exclude.append(raw[1:])
        else:
            include.append(raw)
    return include, exclude


def _hidden_ok(path: Path, allow_hidden: bool) -> bool:
    if allow_hidden:
        return True
    return not any(part.startswith(".") for part in path.parts)


def _glob_ok(rel: str, include: list[str], exclude: list[str]) -> bool:
    name = os.path.basename(rel)
    for pattern in exclude:
        if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(name, pattern):
            return False
    if not include:
        return True
    return any(
        fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(name, pattern)
        for pattern in include
    )


def _iter_files(
    root: Path, include: list[str], exclude: list[str], hidden: bool
) -> Iterator[Path]:
    if root.is_file():
        if _hidden_ok(root, hidden):
            yield root
        return
    if not root.is_dir():
        return
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        if not hidden:
            dirnames[:] = [name for name in dirnames if not name.startswith(".")]
        for name in filenames:
            path = current / name
            rel = str(path.relative_to(root)) if path != root else name
            if not _hidden_ok(Path(rel), hidden):
                continue
            if _glob_ok(rel, include, exclude):
                yield path


def _print_json_match(path: Path, line_no: int, line: str) -> None:
    payload = {
        "type": "match",
        "data": {
            "path": {"text": str(path)},
            "lines": {"text": line},
            "line_number": line_no,
            "absolute_offset": 0,
            "submatches": [],
        },
    }
    sys.stdout.write(json.dumps(payload) + "\n")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    if args.version:
        sys.stdout.write("ripgrep 14.1.1 (onyx-shim)\n")
        return 0
    include, exclude = _split_globs([*args.glob, *args.iglob])
    rest = list(args.rest)
    pattern = ""
    targets: list[str] = ["."]
    if args.files:
        if rest:
            targets = rest
    elif rest:
        pattern = rest[0]
        targets = rest[1:] or ["."]

    try:
        compiled = (
            re.compile(pattern, re.IGNORECASE if args.ignore_case else 0)
            if pattern
            else None
        )
    except re.error:
        return 2

    matched = False
    try:
        for target in targets:
            root = Path(target)
            for path in _iter_files(root, include, exclude, args.hidden):
                if args.files:
                    sys.stdout.write(str(path) + "\n")
                    matched = True
                    continue
                if compiled is None:
                    continue
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                count = 0
                for line_no, line in enumerate(text.splitlines(), start=1):
                    if not compiled.search(line):
                        continue
                    matched = True
                    if args.files_with_matches:
                        sys.stdout.write(str(path) + "\n")
                        break
                    if args.json:
                        _print_json_match(path, line_no, line)
                    else:
                        prefix = f"{path}:{line_no}:" if args.n else f"{path}:"
                        sys.stdout.write(prefix + line + "\n")
                    count += 1
                    if args.max_count is not None and count >= args.max_count:
                        break
    except OSError:
        return 2
    return 0 if matched or args.files else 1


if __name__ == "__main__":
    raise SystemExit(main())
