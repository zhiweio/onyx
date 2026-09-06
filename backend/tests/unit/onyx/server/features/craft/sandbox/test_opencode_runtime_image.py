"""Image contract: Craft sandboxes run OpenCode only."""

from __future__ import annotations

from tests.common.paths import find_ancestor_containing

REPO_ROOT = find_ancestor_containing("deployment")
IMAGE = (
    REPO_ROOT
    / "backend"
    / "onyx"
    / "server"
    / "features"
    / "build"
    / "sandbox"
    / "image"
)


def test_dockerfile_is_opencode_only() -> None:
    text = (IMAGE / "Dockerfile").read_text()
    assert "opencode serve" in (IMAGE / "entrypoint.sh").read_text()
    assert "ARG OPENCODE_VERSION=" in text
    assert "PI_CODING_AGENT_VERSION" not in text
    assert "pi-coding-agent" not in text
    assert "pi_rpc_tunnel" not in text
    assert (IMAGE / "pi_rpc_tunnel.mjs").exists() is False


def test_entrypoint_always_starts_opencode_serve() -> None:
    text = (IMAGE / "entrypoint.sh").read_text()
    assert "opencode serve --hostname 0.0.0.0" in text
    assert "CRAFT_AGENT_RUNTIME" not in text
    assert "pi_rpc_tunnel" not in text
    assert "pi-rpc-tunnel" not in text
