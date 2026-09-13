"""Shared session-workspace setup script for the Docker and Kubernetes
sandbox managers.

The script is replay-safe: the whole setup is serialized per session with an
in-sandbox ``flock``, and an in-progress marker distinguishes a partial
directory from a complete workspace. Setup stays small: empty ``outputs/`` and
``attachments/`` (or links to the parent job session), plus the session venv
and agent config. It does not create job trees or seed PLAN/TODO/MEMORY files.
The web app stays lazy too: it writes the tamper-hardened ``start-webapp.sh``
(when the session has a port) but never scaffolds the template, installs
dependencies, or starts a dev server itself. Re-running the script after an
interruption converges on the same completed workspace.
"""

import base64
import shlex
from pathlib import Path
from uuid import UUID

from onyx.server.features.build.sandbox.nextjs_dev import (
    build_webapp_script_write_snippet,
)
from onyx.server.features.build.sandbox.util.agent_instructions import (
    ATTACHMENTS_SECTION_CONTENT,
)

_RG_SHIM_SOURCE = Path(__file__).with_name("ripgrep_shim.py")
_RG_SHIM_DEST = "/workspace/.venv/bin/rg"

SESSIONS_ROOT = "/workspace/sessions"
MANAGED_SKILLS_PATH = "/workspace/managed/skills"
MANAGED_USER_LIBRARY_PATH = "/workspace/managed/user_library"

# Present inside a session directory while setup is running; its presence on
# an existing directory means the workspace is partial, not ready. Legacy
# workspaces (created before the marker existed) have no marker and read as
# complete.
SETUP_IN_PROGRESS_MARKER = ".setup-in-progress"

# Last line the setup script prints. Callers MUST verify it in the exec
# output: the Kubernetes exec client returns buffered output without raising
# when its timeout lapses (and never raises on a nonzero exit), so the
# sentinel is the only reliable success signal.
WORKSPACE_SETUP_COMPLETE_SENTINEL = "ONYX_WORKSPACE_SETUP_COMPLETE"


def build_workspace_exists_check_script(session_path: str) -> str:
    """Emit ``WORKSPACE_FOUND`` only for a complete workspace: the outputs
    directory exists and no in-progress marker is present."""
    return (
        f'if [ -d "{session_path}/outputs" ] && '
        f'[ ! -f "{session_path}/{SETUP_IN_PROGRESS_MARKER}" ]; '
        f'then echo "WORKSPACE_FOUND"; else echo "WORKSPACE_MISSING"; fi'
    )


def shared_parent_workspace_paths(
    share_workspace_from: UUID | str | None,
) -> tuple[str | None, str | None]:
    """Return parent ``outputs/`` and ``attachments/`` paths for a job lane."""
    if share_workspace_from is None:
        return None, None
    parent = f"{SESSIONS_ROOT}/{share_workspace_from}"
    return f"{parent}/outputs", f"{parent}/attachments"


def _shared_or_local_dir_snippet(
    session_path: str, name: str, shared_path: str | None
) -> str:
    """Link ``name`` to a parent session directory, or create a local one."""
    dest = f"{session_path}/{name}"
    if not shared_path:
        return f"mkdir -p {dest}\n"
    quoted = shlex.quote(shared_path.rstrip("/"))
    return f"""
mkdir -p {quoted}
if [ -e {dest} ] && [ ! -L {dest} ]; then
  if [ -n "$(ls -A {dest} 2>/dev/null)" ]; then
    echo "Refusing to replace a real {name} directory with a shared link"
    exit 1
  fi
  rmdir {dest}
fi
ln -sfn {quoted} {dest}
"""


def build_shared_workspace_dirs_snippet(
    session_path: str,
    share_workspace_from: UUID | str | None,
) -> str:
    """Link ``outputs/`` and ``attachments/`` to the parent job session."""
    shared_outputs, shared_attachments = shared_parent_workspace_paths(
        share_workspace_from
    )
    if shared_outputs is None:
        return ""
    return _shared_or_local_dir_snippet(
        session_path, "outputs", shared_outputs
    ) + _shared_or_local_dir_snippet(session_path, "attachments", shared_attachments)


def build_session_workspace_setup_script(
    session_path: str,
    agents_md: str,
    session_opencode_config_json: str,
    nextjs_port: int | None,
    shared_outputs_path: str | None = None,
    shared_attachments_path: str | None = None,
) -> str:
    """Build the shell script that creates a session workspace.

    Headless callers (scheduled tasks) pass ``nextjs_port=None`` — the agent's
    tools work without a dev server, and no ``start-webapp.sh`` is written.
    Job lanes pass ``shared_outputs_path`` and ``shared_attachments_path`` so
    those directories point at the parent session. The virtualenv lives at
    ``{session_path}/.venv``, never under ``outputs/``.
    """
    webapp_script_write_snippet = (
        # Lazy provisioning: write start-webapp.sh, but don't scaffold
        # outputs/web, install, or start a dev server here.
        build_webapp_script_write_snippet(session_path, nextjs_port)
        if nextjs_port is not None
        else ""
    )
    outputs_snippet = _shared_or_local_dir_snippet(
        session_path, "outputs", shared_outputs_path
    )
    attachments_snippet = _shared_or_local_dir_snippet(
        session_path, "attachments", shared_attachments_path
    )
    ripgrep_fallback_snippet = (
        "if ! command -v rg >/dev/null 2>&1 || ! rg --version >/dev/null 2>&1; then\n"
        "  mkdir -p /workspace/.venv/bin /home/sandbox/.opencode/bin\n"
        f"  printf '%s' {shlex.quote(_RG_SHIM_SOURCE.read_text())} > {_RG_SHIM_DEST}\n"
        f"  chmod 755 {_RG_SHIM_DEST}\n"
        f"  cp {_RG_SHIM_DEST} /home/sandbox/.opencode/bin/rg\n"
        "  chmod 755 /home/sandbox/.opencode/bin/rg\n"
        "fi\n"
    )
    attachments_section_b64 = base64.b64encode(
        ATTACHMENTS_SECTION_CONTENT.encode()
    ).decode()

    return f"""
set -e

# Serialize workspace *materialization* per session with an flock: a concurrent
# replay blocks here and then re-runs over the completed workspace, converging
# instead of racing. Nothing spawned here outlives the setup, so nothing can
# inherit fd 8 and hold the lock open.
(
flock -x 8
set -e

echo "Creating session directory: {session_path}"
mkdir -p {session_path}
chmod 755 {session_path}
touch {session_path}/{SETUP_IN_PROGRESS_MARKER}
{outputs_snippet}
{attachments_snippet}
mkdir -p {session_path}/.venv-lock
if [ ! -x {session_path}/.venv/bin/python ]; then
  python3 -m venv --system-site-packages {session_path}/.venv
fi
printf '%s\\n' 'export PATH="{session_path}/.venv/bin:$PATH"' 'export VIRTUAL_ENV="{session_path}/.venv"' > {session_path}/.session-env
mkdir -p {session_path}/bin
ln -sfn {session_path}/.venv/bin/python {session_path}/bin/python
ln -sfn {session_path}/.venv/bin/pip {session_path}/bin/pip

# DO NOT mkdir /workspace/managed/skills or /workspace/managed/user_library
# here — the push daemon swaps these paths via os.rename(symlink, mount),
# which fails if the mount is a real directory. Dangling until the first
# push lands is fine; nothing reads these during the rest of setup.
mkdir -p {session_path}/.opencode
ln -sfn {MANAGED_SKILLS_PATH} {session_path}/.opencode/skills
echo "Linked skills to {MANAGED_SKILLS_PATH}"
ln -sfn {MANAGED_USER_LIBRARY_PATH} {session_path}/user_library
echo "Linked user_library to {MANAGED_USER_LIBRARY_PATH}"

# Write agent instructions
echo "Writing AGENTS.md"
printf '%s' {shlex.quote(agents_md)} > {session_path}/AGENTS.md
if [ -n "$(find {session_path}/attachments -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]; then
  if ! grep -q "## Attachments (PRIORITY)" "{session_path}/AGENTS.md" 2>/dev/null; then
    printf '\\n\\n' >> {session_path}/AGENTS.md
    echo '{attachments_section_b64}' | base64 -d >> {session_path}/AGENTS.md
  fi
fi

printf '%s' {shlex.quote(session_opencode_config_json)} > {session_path}/opencode.json

{webapp_script_write_snippet}

{ripgrep_fallback_snippet}

rm -f {session_path}/{SETUP_IN_PROGRESS_MARKER}
echo "Workspace materialization complete"
) 8>{session_path}.setup.lock

echo "{WORKSPACE_SETUP_COMPLETE_SENTINEL}"
"""
