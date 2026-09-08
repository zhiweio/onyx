from pathlib import Path

import pytest

from onyx.server.features.build.sandbox.ripgrep_shim import main
from onyx.server.features.build.sandbox.session_workspace import (
    build_session_workspace_setup_script,
)


def test_version_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--version"]) == 0
    assert "ripgrep" in capsys.readouterr().out


def test_files_mode_lists_matching_paths(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "SKILL.md").write_text("name: company-search\n")
    (tmp_path / "notes.txt").write_text("skip\n")
    code = main(["--no-config", "--files", "--glob", "SKILL.md", str(tmp_path)])
    captured = capsys.readouterr()
    assert code == 0
    assert "SKILL.md" in captured.out
    assert "notes.txt" not in captured.out


def test_grep_json_finds_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "SKILL.md").write_text("Search company knowledge\n")
    code = main(
        [
            "--no-config",
            "--json",
            "--hidden",
            "--no-messages",
            "company",
            str(tmp_path),
        ]
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "company" in captured.out
    assert '"type": "match"' in captured.out or '"type":"match"' in captured.out


def test_grep_no_match_exits_one(tmp_path: Path) -> None:
    (tmp_path / "SKILL.md").write_text("nothing here\n")
    assert main(["--no-config", "zzzz-missing", str(tmp_path)]) == 1


def test_setup_script_installs_rg_shim_when_missing() -> None:
    script = build_session_workspace_setup_script(
        session_path="/workspace/sessions/00000000-0000-0000-0000-000000000000",
        agents_md="hi",
        session_opencode_config_json="{}",
        nextjs_port=None,
    )
    assert "command -v rg" in script
    assert "/workspace/.venv/bin/rg" in script
    assert "/home/sandbox/.opencode/bin/rg" in script
    assert "Minimal ``rg`` stand-in" in script
