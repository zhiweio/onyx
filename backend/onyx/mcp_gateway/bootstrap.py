"""Idempotent install of built-in MCP families from process env keys."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from onyx.configs.app_configs import (
    HITHINK_FINANCE_API_KEY,
    QCC_AGENT_API_KEY,
    ZHIHUIYA_MCP_API_KEY,
)
from onyx.db.models import User
from onyx.mcp_gateway.service import is_gateway_enabled
from onyx.server.features.mcp.gateway_bind import create_org_servers_from_pack_family
from onyx.server.features.mcp.models import MCPFromPackRequest
from onyx.utils.logger import setup_logger

logger = setup_logger()

_FAMILY_KEYS: tuple[tuple[str, str], ...] = (
    ("hithink-finance", HITHINK_FINANCE_API_KEY),
    ("qichacha", QCC_AGENT_API_KEY),
    ("zhihuiya", ZHIHUIYA_MCP_API_KEY),
)


def _first_user(db_session: Session) -> User | None:
    return db_session.scalars(select(User).order_by(User.created_at).limit(1)).first()


def _mark_public(
    *,
    mcp_server: Any,
    acting_user: User,  # noqa: ARG001
    is_public: bool | None,
    user_ids: list[UUID] | None,  # noqa: ARG001
    group_ids: list[int] | None,  # noqa: ARG001
    is_new: bool,  # noqa: ARG001
    db_session: Session,  # noqa: ARG001
) -> None:
    mcp_server.is_public = True if is_public is None else is_public


def bootstrap_builtin_mcp_families(db_session: Session) -> None:
    """Create or refresh family servers when the matching env key is set.

    Skips tool discovery so API startup does not wait on every remote MCP.
    The first Chat or Craft turn that selects a server discovers its tools.
    """
    if not is_gateway_enabled():
        return
    user = _first_user(db_session)
    if user is None:
        logger.info("Skip built-in MCP family bootstrap: no user yet")
        return

    apply_access: Callable[..., None] = _mark_public
    for pack_slug, api_key in _FAMILY_KEYS:
        if not api_key:
            continue
        try:
            created = create_org_servers_from_pack_family(
                db_session,
                user,
                MCPFromPackRequest(
                    pack_slug=pack_slug,
                    credentials={"api_key": api_key},
                    is_public=True,
                ),
                apply_access=apply_access,
                discover_tools=False,
            )
            logger.notice(
                "Bootstrapped MCP family %s (%s servers)",
                pack_slug,
                len(created),
            )
        except Exception:
            logger.exception("Failed to bootstrap MCP family %s", pack_slug)
