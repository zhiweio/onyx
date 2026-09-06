from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from onyx.skills.built_in import BUILTIN_SKILLS_PATH

_SCRIPT = BUILTIN_SKILLS_PATH / "document-ingest" / "scripts" / "ingest.py"
_SPEC = importlib.util.spec_from_file_location("document_ingest_script", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
ingest = importlib.util.module_from_spec(_SPEC)
sys.modules["document_ingest_script"] = ingest
_SPEC.loader.exec_module(ingest)


def test_classify_parser_routes_tables_and_scans() -> None:
    assert ingest.classify_parser(Path("ledger.xlsx")) == "pandas"
    assert ingest.classify_parser(Path("invoices.csv")) == "pandas"
    assert ingest.classify_parser(Path("note.docx")) == "python-docx"
    assert ingest.classify_parser(Path("deck.pptx")) == "python-pptx"
    assert ingest.classify_parser(Path("scan.pdf")) == "pdfplumber"
    assert ingest.classify_parser(Path("receipt.png")) == "vision"
    assert ingest.classify_parser(Path("readme.md")) == "skip"


def test_dry_run_writes_no_files(tmp_path: Path) -> None:
    source = tmp_path / "project"
    source.mkdir()
    (source / "a.xlsx").write_bytes(b"not-a-real-xlsx")
    out = tmp_path / "outputs"
    result = ingest.run_ingest(roots=[source], out_dir=out, dry_run=True)
    assert len(result.entries) == 1
    assert result.entries[0].status == "planned"
    assert result.entries[0].parser == "pandas"
    assert not (out / "ingest" / "MANIFEST.json").exists()


def test_csv_extract_writes_manifest(tmp_path: Path) -> None:
    source = tmp_path / "project"
    source.mkdir()
    (source / "payables.csv").write_text("vendor,amount\nA,10\nB,20\n", encoding="utf-8")
    out = tmp_path / "outputs"
    result = ingest.run_ingest(roots=[source], out_dir=out)
    assert result.entries[0].status == "ok"
    assert result.entries[0].parser == "pandas"
    manifest = out / "ingest" / "MANIFEST.json"
    assert manifest.is_file()
    extracted = out / "extracted" / f"{result.entries[0].file_id}.json"
    assert extracted.is_file()
    text = extracted.read_text(encoding="utf-8")
    assert "vendor" in text
    assert "row_count" in text
