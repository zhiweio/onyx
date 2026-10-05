"""codex per-sandbox configuration: config.toml + env file builders.

The daemon bridge exports ``CODEX_ENV_FILE`` into the codex child, and
codex reads ``$CODEX_HOME/config.toml``. The host writes both next to the
session config it already manages (``regenerate_session_config``
equivalents for the codex runtime call these builders).

v1 scope: gateway provider (chat wire API), model pin, workspace-write
sandbox, MCP servers from the craft-enabled set when codex's http-mcp
shape supports headers; otherwise MCP is omitted and the capability
matrix says so.
"""

from __future__ import annotations

from typing import Any

from onyx.server.features.build.sandbox.models import CraftMCPServerConfig

GATEWAY_PROVIDER_ID = "onyx-gateway"
GATEWAY_API_KEY_ENV = "ONYX_CODEX_API_KEY"


def build_codex_config_toml(
    *,
    gateway_base_url: str,
    model: str,
    mcp_servers: list[CraftMCPServerConfig] | None = None,
) -> str:
    """Minimal config.toml driving codex at the Onyx gateway.

    v1 omits ``[mcp_servers]``: codex's http-mcp in the pinned version
    cannot carry the per-request headers our platform bridge requires
    (session tag + auth), so a half-configured entry would produce broken
    tool calls. External tools stay reachable through the gateway once a
    header-capable codex release is pinned (see the P2 plan's risk log).
    ``mcp_servers`` is accepted so the caller shape is already final."""
    _ = mcp_servers
    lines = [
        f'model = "{model}"',
        f'model_provider = "{GATEWAY_PROVIDER_ID}"',
        'approval_policy = "never"',
        'sandbox_mode = "workspace-write"',
        "",
        f"[model_providers.{GATEWAY_PROVIDER_ID}]",
        'name = "Onyx Gateway"',
        f'base_url = "{gateway_base_url.rstrip("/")}"',
        'wire_api = "chat"',
        f'env_key = "{GATEWAY_API_KEY_ENV}"',
    ]
    return "\n".join(lines) + "\n"


def build_codex_env_file(api_key: str) -> str:
    """KEY=VALUE lines the daemon exports into the codex child."""
    return f"{GATEWAY_API_KEY_ENV}={api_key}\n"


def build_thread_start_params(
    *,
    cwd: str,
    base_instructions: str,
    model: str | None,
    reasoning_effort: str | None = None,
    user_instructions: str = "",
) -> dict[str, Any]:
    """``thread/start`` params for a craft turn (qm-verified shape)."""
    features: dict[str, Any] = {
        "shell_tool": True,
        "unified_exec": False,
        "shell_snapshot": True,
        "goals": False,
        "apps": False,
        "plugins": False,
        "browser_use": False,
        "computer_use": False,
        "image_generation": False,
        "in_app_browser": False,
        "multi_agent": False,
        "request_permissions_tool": False,
        "tool_suggest": False,
    }
    config: dict[str, Any] = {
        "web_search": "disabled",  # craft routes search through platform tools
        "features": features,
    }
    if reasoning_effort in {"low", "medium", "high", "xhigh"}:
        config["model_reasoning_effort"] = reasoning_effort
    params: dict[str, Any] = {
        "cwd": cwd,
        "approvalPolicy": "never",
        "sandbox": "workspace-write",
        "ephemeral": True,
        "baseInstructions": base_instructions,
        "experimentalRawEvents": True,
        "environments": [],
        "config": config,
    }
    if model:
        params["model"] = model
    if user_instructions:
        params["developerInstructions"] = user_instructions
    return params


def build_turn_input(
    prompt: str, attachments: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """``turn/start`` input array: text first, then image data-URLs."""
    items: list[dict[str, Any]] = [
        {"type": "text", "text": prompt, "text_elements": []}
    ]
    items.extend(attachments or [])
    return items
