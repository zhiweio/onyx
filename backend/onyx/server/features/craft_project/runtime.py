from uuid import UUID

from sqlalchemy.orm import Session

from onyx.db.craft_project import build_project_fileset, require_project_for_user
from onyx.db.models import User
from onyx.server.features.build.sandbox.base import SandboxManager
from onyx.utils.logger import setup_logger

logger = setup_logger()


def project_has_workspace_brief(
    *,
    description: str,
    instructions: str | None,
    file_names: list[str],
) -> bool:
    """True when the project has content the agent should see on disk."""
    return bool(description.strip() or (instructions or "").strip() or file_names)


def render_project_markdown(
    name: str, description: str, instructions: str | None, file_names: list[str]
) -> str:
    lines = [
        f"# Project: {name}",
        "",
        description or "",
        "",
        "Shared project files live in `project/`. Read them at the start of the turn.",
        "Put reusable deliverables in `outputs/` so they stay with this project.",
    ]
    if instructions and instructions.strip():
        lines.extend(["", "## Instructions", "", instructions.strip()])
    lines.extend(["", "## Files"])
    if file_names:
        lines.extend(f"- `{name}`" for name in file_names)
    else:
        lines.append("- (no files yet)")
    return "\n".join(lines).strip() + "\n"


def write_project_to_session(
    db_session: Session,
    sandbox_manager: SandboxManager,
    sandbox_id: UUID,
    session_id: UUID,
    project_id: UUID,
    user: User,
) -> None:
    project = require_project_for_user(db_session, project_id, user)
    files = build_project_fileset(db_session, project.id)
    names = sorted(files.keys())
    if project_has_workspace_brief(
        description=project.description,
        instructions=project.instructions,
        file_names=names,
    ):
        sandbox_manager.write_sandbox_file(
            sandbox_id,
            f"sessions/{session_id}/PROJECT.md",
            render_project_markdown(
                project.name, project.description, project.instructions, names
            ),
        )
    if files:
        result = sandbox_manager.push_to_sandbox(
            sandbox_id=sandbox_id,
            mount_path=f"/workspace/sessions/{session_id}/project",
            files=files,
        )
        if result.failures:
            logger.warning(
                "Project file push failed for session %s: %s",
                session_id,
                result.failures[0].detail,
            )
