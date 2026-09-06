"""Push Word report template assets into a sandbox.

A markdown template needs nothing at runtime — its outline is inlined into
SCENARIO.md. A Word template is a binary the agent has to open, so the asset is
pushed to a managed mount and SCENARIO.md points at that path.

The mount mirrors ``user_library``: a sandbox-root directory that every session
can read.
"""

from __future__ import annotations

from typing import Final
from uuid import UUID

from onyx.db.enums import ReportTemplateKind
from onyx.db.models import ReportTemplate
from onyx.file_store.file_store import get_default_file_store
from onyx.report_templates.docx_template import sandbox_template_filename
from onyx.server.features.build.sandbox.base import SandboxManager
from onyx.server.features.build.sandbox.models import FileSet
from onyx.utils.logger import setup_logger

logger = setup_logger()

REPORT_TEMPLATE_MOUNT_PATH: Final[str] = "/workspace/managed/report_templates"
# The path the agent sees. The mount is sandbox-root, so it is stable across
# sessions and safe to name in SCENARIO.md.
REPORT_TEMPLATE_AGENT_DIR: Final[str] = "/workspace/managed/report_templates"


def agent_template_path(template: ReportTemplate) -> str:
    return f"{REPORT_TEMPLATE_AGENT_DIR}/{sandbox_template_filename(template.slug)}"


def build_report_template_fileset(templates: list[ReportTemplate]) -> FileSet:
    """Read each DOCX template's asset into a ``{filename: bytes}`` map.

    A template whose blob cannot be read is skipped with a warning rather than
    failing session setup: a missing asset must not block the whole session.
    """
    files: FileSet = {}
    file_store = get_default_file_store()
    for template in templates:
        if template.kind is not ReportTemplateKind.DOCX:
            continue
        if template.asset_file_id is None:
            continue
        try:
            files[sandbox_template_filename(template.slug)] = file_store.read_file(
                template.asset_file_id
            ).read()
        except Exception:
            logger.warning(
                "Failed to read Word template asset for '%s' (%s), skipping",
                template.slug,
                template.asset_file_id,
                exc_info=True,
            )
    return files


def push_report_templates_to_sandbox(
    sandbox_manager: SandboxManager,
    sandbox_id: UUID,
    templates: list[ReportTemplate],
) -> None:
    """Push the given Word templates to a sandbox, replacing the mount."""
    files = build_report_template_fileset(templates)
    if not files:
        return
    result = sandbox_manager.push_to_sandbox(
        sandbox_id=sandbox_id,
        mount_path=REPORT_TEMPLATE_MOUNT_PATH,
        files=files,
    )
    if result.failures:
        logger.warning(
            "Failed to push report templates to sandbox %s: %s",
            sandbox_id,
            result.failures,
        )
