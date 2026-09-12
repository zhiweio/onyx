"""Shipped Kimi official skills stay parseable and mapped to gallery categories."""

from __future__ import annotations

import ast
import json
import re
import sys
from collections import Counter

from onyx.db.enums import SystemCatalogCategory
from onyx.skills.built_in import BUILT_IN_SKILLS, BUILTIN_SKILLS_PATH
from onyx.skills.kimi_official import KIMI_CLI_SKILL_SLUGS, KIMI_OFFICIAL_SKILLS
from onyx.skills.metadata import parse_skill_document
from onyx.system_catalog.builtin.manifest import BUILT_IN_SKILL_ENTRIES

_SANDBOX_IMAGE_DIR = (
    BUILTIN_SKILLS_PATH.parents[1] / "server/features/build/sandbox/image"
)

# Import name -> pip requirement name for third-party modules used by Kimi scripts.
_PYTHON_IMPORT_TO_REQUIREMENT: dict[str, str] = {
    "bs4": "beautifulsoup4",
    "dotenv": "python-dotenv",
    "markdown": "markdown",
    "matplotlib": "matplotlib",
    "numpy": "numpy",
    "openpyxl": "openpyxl",
    "pandas": "pandas",
    "playwright": "playwright",
    "psycopg2": "psycopg2-binary",
    "requests": "requests",
    "scipy": "scipy",
    "statsmodels": "statsmodels",
    "xhs": "xhs",
    "yaml": "pyyaml",
}

_NODE_BUILTIN_OR_RELATIVE = {
    "assert",
    "buffer",
    "child_process",
    "crypto",
    "events",
    "fs",
    "fs/promises",
    "http",
    "https",
    "module",
    "os",
    "path",
    "process",
    "stream",
    "url",
    "util",
}

_JS_REQUIRE_RE = re.compile(r"""(?:require\(\s*|from\s+)['"]([^'"]+)['"]""")


def test_kimi_official_slugs_are_unique() -> None:
    slugs = [skill.slug for skill in KIMI_OFFICIAL_SKILLS]
    assert slugs == sorted(set(slugs), key=slugs.index)


def test_kimi_official_skills_are_registered_and_parse() -> None:
    for skill in KIMI_OFFICIAL_SKILLS:
        definition = BUILT_IN_SKILLS[skill.slug]
        document = parse_skill_document(
            (definition.source_dir / "SKILL.md").read_bytes(),
            directory_name=skill.slug,
        )
        assert document.metadata.name == skill.slug
        assert document.instructions_markdown


def test_kimi_official_skills_are_in_the_gallery_manifest() -> None:
    by_slug = {entry.slug: entry for entry in BUILT_IN_SKILL_ENTRIES}
    for skill in KIMI_OFFICIAL_SKILLS:
        entry = by_slug[skill.slug]
        assert entry.built_in_skill_id == skill.slug
        assert entry.category is skill.category
        assert entry.name == skill.name


def test_kimi_official_skills_cover_requested_categories() -> None:
    counts = Counter(skill.category for skill in KIMI_OFFICIAL_SKILLS)
    assert counts[SystemCatalogCategory.CONTENT] >= 1
    assert counts[SystemCatalogCategory.ACADEMIC] >= 1
    assert counts[SystemCatalogCategory.REPORT] >= 1
    assert counts[SystemCatalogCategory.GRAPHIC] >= 1
    assert counts[SystemCatalogCategory.DEV_TOOL] == 9
    assert KIMI_CLI_SKILL_SLUGS == {
        "codex-worker",
        "feature-smoke-test",
        "gen-changelog",
        "gen-docs",
        "gen-rust",
        "pull-request",
        "release",
        "translate-docs",
        "worktree-status",
    }


def _requirement_names(in_text: str) -> set[str]:
    names: set[str] = set()
    for line in in_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        names.add(re.split(r"[<>=\[]", stripped, maxsplit=1)[0].strip().lower())
    return names


def _top_level_python_imports(source: str) -> set[str]:
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def _js_package_names(source: str) -> set[str]:
    names: set[str] = set()
    for match in _JS_REQUIRE_RE.finditer(source):
        spec = match.group(1)
        if spec.startswith(".") or spec.startswith("node:"):
            continue
        if spec in _NODE_BUILTIN_OR_RELATIVE:
            continue
        if spec.startswith("@"):
            parts = spec.split("/")
            names.add("/".join(parts[:2]))
            continue
        names.add(spec.split("/")[0])
    return names


def test_kimi_python_script_imports_are_in_the_sandbox_venv() -> None:
    reqs = _requirement_names(
        (_SANDBOX_IMAGE_DIR / "initial-requirements.in").read_text(encoding="utf-8")
    )
    stdlib = set(sys.stdlib_module_names) | {"__future__"}
    missing: list[str] = []
    unmapped: list[str] = []
    for skill in KIMI_OFFICIAL_SKILLS:
        for script in BUILT_IN_SKILLS[skill.slug].source_dir.rglob("*.py"):
            imports = _top_level_python_imports(script.read_text(encoding="utf-8"))
            for name in sorted(imports - stdlib):
                requirement = _PYTHON_IMPORT_TO_REQUIREMENT.get(name)
                if requirement is None:
                    unmapped.append(f"{skill.slug}:{script.name}:{name}")
                    continue
                if requirement not in reqs:
                    missing.append(f"{skill.slug}:{script.name}:{requirement}")
    assert not unmapped, f"Map new Kimi imports to pip names: {unmapped}"
    assert not missing, f"Add Kimi script deps to initial-requirements.in: {missing}"


def test_kimi_js_script_packages_are_in_the_sandbox_image() -> None:
    dockerfile = (_SANDBOX_IMAGE_DIR / "Dockerfile").read_text(encoding="utf-8")
    missing: list[str] = []
    for skill in KIMI_OFFICIAL_SKILLS:
        source_dir = BUILT_IN_SKILLS[skill.slug].source_dir
        expected: set[str] = set()
        for script in source_dir.rglob("*"):
            if script.suffix not in {".js", ".mjs"}:
                continue
            expected.update(_js_package_names(script.read_text(encoding="utf-8")))
        package_json = source_dir / "package.json"
        scripts_package_json = source_dir / "scripts" / "package.json"
        for manifest in (package_json, scripts_package_json):
            if not manifest.is_file():
                continue
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            expected.update(payload.get("dependencies", {}))
        missing.extend(
            f"{skill.slug}:{package}"
            for package in sorted(expected)
            if f"{package}@" not in dockerfile and f" {package} " not in dockerfile
        )
    assert not missing, f"Add Kimi npm deps to the sandbox Dockerfile: {missing}"


def test_kimi_sandbox_image_exposes_playwright_and_esm_resolution() -> None:
    dockerfile = (_SANDBOX_IMAGE_DIR / "Dockerfile").read_text(encoding="utf-8")
    assert "PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright" in dockerfile
    assert "ln -sfn /usr/local/lib/node_modules /node_modules" in dockerfile
    assert "playwright install chromium" in dockerfile
    assert "playwright@1.58.0" in dockerfile
    assert "playwright==1.58.0" in (
        _SANDBOX_IMAGE_DIR / "initial-requirements.in"
    ).read_text(encoding="utf-8")
