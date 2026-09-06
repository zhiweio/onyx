"""Copy a published catalog entry into a user-owned runtime row.

A fork is an ordinary user resource: it is editable, it is not touched when the
upstream entry is unpublished, and it keeps ``system_<kind>_id`` /
``system_<kind>_version`` only so the UI can offer "a newer version exists".
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from onyx.configs.constants import FileOrigin
from onyx.db.enums import ReportTemplateKind
from onyx.db.models import (
    ReportTemplate,
    Scenario,
    Scenario__Skill,
    Skill,
    SystemReportTemplate,
    SystemScenario,
    SystemSkill,
    User,
)
from onyx.db.report_template import SLUG_MAX as REPORT_TEMPLATE_SLUG_MAX
from onyx.db.scenario import SCENARIO_NAME_MAX
from onyx.db.system_catalog.constants import SKILL_NAME_MAX, require_published
from onyx.db.system_catalog.publish import (
    find_projected_scenario,
    find_projected_skill,
)
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.file_store.file_store import FileStore, get_default_file_store
from onyx.report_templates.docx_template import DOCX_CONTENT_TYPE
from onyx.skills.built_in import BUILT_IN_SKILLS
from onyx.skills.bundle import (
    SKILL_MD_NAME,
    compute_bundle_sha256,
    normalize_custom_bundle,
)
from onyx.skills.content import read_custom_skill_bundle_bytes
from onyx.skills.ingest import save_skill_bundle_bytes
from onyx.skills.metadata import parse_skill_md_frontmatter, serialize_skill_md

COPY_SUFFIX = "-copy"
# Bound the rename search so a pathological account cannot spin here.
MAX_COPY_ATTEMPTS = 100
# Mirrors onyx.skills.push._is_excluded: these never belong in a bundle.
_EXCLUDED_BUNDLE_DIRS = frozenset({"__pycache__", ".git"})


def _taken_skill_names(db_session: Session, user: User) -> set[str]:
    """Names the user could have enabled at the same time as the fork.

    Workspace-owned skills (built-ins and catalog projections) are visible to
    everyone, and ``uq_user_skill_preference_name`` plus the sandbox fileset
    assembler both reject two enabled skills sharing a name.
    """
    rows = db_session.scalars(
        select(Skill.name).where(
            (Skill.author_user_id == user.id) | (Skill.author_user_id.is_(None))
        )
    ).all()
    return set(rows) | set(BUILT_IN_SKILLS)


def _unique_skill_name(base: str, taken: set[str]) -> str:
    if base not in taken:
        return base
    for attempt in range(1, MAX_COPY_ATTEMPTS + 1):
        suffix = COPY_SUFFIX if attempt == 1 else f"{COPY_SUFFIX}-{attempt}"
        stem = base[: SKILL_NAME_MAX - len(suffix)]
        candidate = f"{stem}{suffix}"
        if candidate not in taken:
            return candidate
    raise OnyxError(
        OnyxErrorCode.CONFLICT,
        f"Could not find a free name for a copy of '{base}'",
    )


def _unique_report_template_slug(db_session: Session, base: str) -> str:
    taken = set(db_session.scalars(select(ReportTemplate.slug)).all())
    if base not in taken:
        return base
    for attempt in range(1, MAX_COPY_ATTEMPTS + 1):
        suffix = "_copy" if attempt == 1 else f"_copy_{attempt}"
        stem = base[: REPORT_TEMPLATE_SLUG_MAX - len(suffix)]
        candidate = f"{stem}{suffix}"
        if candidate not in taken:
            return candidate
    raise OnyxError(
        OnyxErrorCode.CONFLICT,
        f"Could not find a free template ID for a copy of '{base}'",
    )


def _package_builtin_skill_dir(source_dir: Path) -> bytes:
    """Zip an on-disk built-in skill so a fork owns an editable copy.

    Forks are bundle-backed by design: the user must be able to edit content
    that otherwise only ships with the deployment.
    """
    if not source_dir.is_dir():
        raise OnyxError(
            OnyxErrorCode.INTERNAL_ERROR,
            f"Built-in skill content is missing at '{source_dir.name}'",
        )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source_dir.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(source_dir)
            if _EXCLUDED_BUNDLE_DIRS.intersection(relative.parts):
                continue
            archive.writestr(relative.as_posix(), path.read_bytes())
    return buffer.getvalue()


def _bundle_bytes_for_catalog_skill(
    db_session: Session, entry: SystemSkill, file_store: FileStore
) -> bytes:
    if entry.built_in_skill_id is not None:
        definition = BUILT_IN_SKILLS.get(entry.built_in_skill_id)
        if definition is None:
            raise OnyxError(
                OnyxErrorCode.INTERNAL_ERROR,
                f"Unknown built-in skill '{entry.built_in_skill_id}'",
            )
        if definition.has_template:
            # Templates are rendered per user at push time from live state, so
            # a static copy would silently freeze whatever it captured.
            raise OnyxError(
                OnyxErrorCode.INVALID_INPUT,
                f"'{entry.slug}' is rendered per user and cannot be copied",
            )
        return _package_builtin_skill_dir(definition.source_dir)

    projection = find_projected_skill(db_session, entry)
    if projection is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Catalog entry not found")
    return read_custom_skill_bundle_bytes(projection, file_store)


def fork_system_skill_for_user(
    db_session: Session,
    entry: SystemSkill,
    user: User,
    *,
    file_store: FileStore | None = None,
) -> Skill:
    """Copy a published catalog skill into a personal, editable skill.

    The copy is always renamed: the projection already occupies the entry slug,
    and two enabled skills may not share a name.
    """
    require_published(entry)
    store = file_store or get_default_file_store()

    raw_bundle = _bundle_bytes_for_catalog_skill(db_session, entry, store)
    name = _unique_skill_name(entry.slug, _taken_skill_names(db_session, user))
    # Rewriting through the shared normalizer keeps forks byte-compatible with
    # bundles uploaded by hand.
    normalized = normalize_custom_bundle(raw_bundle)
    renamed = _rewrite_bundle_name(normalized.content, name)

    bundle_file_id = save_skill_bundle_bytes(
        renamed,
        display_name=f"{name}.zip",
        file_store=store,
    )
    try:
        skill = Skill(
            name=name,
            description=entry.description,
            built_in_skill_id=None,
            bundle_file_id=bundle_file_id,
            bundle_sha256=compute_bundle_sha256(renamed),
            is_valid=True,
            author_user_id=user.id,
            public_permission=None,
            system_skill_id=entry.id,
            system_skill_version=entry.version,
        )
        db_session.add(skill)
        db_session.flush()
    except Exception:
        store.delete_file(bundle_file_id, error_on_missing=False)
        raise
    return skill


def _rewrite_bundle_name(bundle_bytes: bytes, name: str) -> bytes:
    """Replace only the frontmatter ``name`` in a bundle's SKILL.md.

    ``rewrite_custom_bundle_skill_md`` replaces the whole document, which would
    drop the built-in's body. A fork must keep its instructions verbatim.
    """
    with zipfile.ZipFile(io.BytesIO(bundle_bytes)) as source:
        frontmatter, body = parse_skill_md_frontmatter(source.read(SKILL_MD_NAME))
        frontmatter["name"] = name
        rewritten = serialize_skill_md(frontmatter, body).encode("utf-8")

        output = io.BytesIO()
        with zipfile.ZipFile(
            output, mode="w", compression=zipfile.ZIP_DEFLATED
        ) as target:
            for info in source.infolist():
                if info.is_dir():
                    continue
                payload = (
                    rewritten
                    if info.filename == SKILL_MD_NAME
                    else source.read(info.filename)
                )
                target.writestr(info.filename, payload)
    return output.getvalue()


def fork_system_report_template_for_user(
    db_session: Session, entry: SystemReportTemplate, user: User
) -> ReportTemplate:
    require_published(entry)
    template = ReportTemplate(
        slug=_unique_report_template_slug(db_session, entry.slug),
        name=entry.name,
        description=entry.description,
        body=entry.body,
        kind=entry.kind,
        placeholders=list(entry.placeholders),
        asset_filename=entry.asset_filename,
        author_user_id=user.id,
        is_builtin=False,
        system_report_template_id=entry.id,
        system_report_template_version=entry.version,
    )
    # A fork owns its asset: the user may edit or delete their copy, which must
    # not disturb the catalog entry's blob.
    if entry.kind is ReportTemplateKind.DOCX and entry.asset_file_id is not None:
        file_store = get_default_file_store()
        payload = file_store.read_file(entry.asset_file_id).read()
        template.asset_file_id = file_store.save_file(
            content=io.BytesIO(payload),
            display_name=f"{template.slug}.docx",
            file_origin=FileOrigin.REPORT_TEMPLATE_ASSET,
            file_type=DOCX_CONTENT_TYPE,
        )
        template.asset_sha256 = entry.asset_sha256
    db_session.add(template)
    try:
        db_session.flush()
    except Exception:
        if template.asset_file_id is not None:
            get_default_file_store().delete_file(
                template.asset_file_id, error_on_missing=False
            )
        raise
    return template


def fork_system_scenario_for_user(
    db_session: Session, entry: SystemScenario, user: User
) -> Scenario:
    """Copy a published catalog scenario into a personal, editable pack.

    Bound skills are left pointing at the shared projections: the user can read
    them already, and forking a pack should not silently clone every skill.
    """
    require_published(entry)
    projection = find_projected_scenario(db_session, entry)
    if projection is None:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "Catalog entry not found")

    scenario = Scenario(
        name=entry.name[:SCENARIO_NAME_MAX],
        description=entry.description,
        author_user_id=user.id,
        public_permission=None,
        rules=dict(projection.rules or {}),
        report_template=projection.report_template,
        system_scenario_id=entry.id,
        system_scenario_version=entry.version,
    )
    db_session.add(scenario)
    db_session.flush()
    for link in sorted(projection.skill_links, key=lambda row: row.sort_order):
        db_session.add(
            Scenario__Skill(
                scenario_id=scenario.id,
                skill_id=link.skill_id,
                sort_order=link.sort_order,
            )
        )
    db_session.flush()
    return scenario
