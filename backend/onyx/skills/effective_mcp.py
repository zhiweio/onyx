"""Resolve the MCP servers a Chat or Craft turn may use."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from onyx.db.mcp import (
    get_mcp_servers_accessible_to_user,
    get_user_connection_configs,
)
from onyx.db.models import MCPCatalogEntry, MCPServer, User
from onyx.server.features.mcp.credentials import user_can_authenticate
from onyx.skills.built_in import BUILT_IN_SKILLS
from onyx.skills.metadata import parse_skill_document
from onyx.skills.models import SkillMetadata
from onyx.utils.logger import setup_logger

logger = setup_logger()


@dataclass(frozen=True)
class SkillMcpSpec:
    required: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()
    groups: dict[str, tuple[str, ...]] = field(default_factory=dict)
    default_group: str | None = None


def _metadata_to_spec(metadata: SkillMetadata) -> SkillMcpSpec:
    groups = {
        name: tuple(slugs)
        for name, slugs in (metadata.mcp_groups or {}).items()
        if slugs
    }
    return SkillMcpSpec(
        required=tuple(metadata.required_mcp or ()),
        optional=tuple(metadata.optional_mcp or ()),
        groups=groups,
        default_group=metadata.default_mcp_group,
    )


def load_skill_mcp_spec(skill_id: str) -> SkillMcpSpec | None:
    definition = BUILT_IN_SKILLS.get(skill_id)
    if definition is None:
        return None
    source_name = "SKILL.md.template" if definition.has_template else "SKILL.md"
    source_path = definition.source_dir / source_name
    if not source_path.is_file():
        return None
    document = parse_skill_document(
        source_path.read_bytes(), directory_name=skill_id
    )
    return _metadata_to_spec(document.metadata)


def slugs_for_skill_spec(spec: SkillMcpSpec) -> set[str]:
    slugs = set(spec.required)
    slugs.update(spec.optional)
    if spec.default_group and spec.default_group in spec.groups:
        slugs.update(spec.groups[spec.default_group])
    return slugs


def catalog_slug_for_server(server: MCPServer) -> str | None:
    entry = server.catalog_entry
    if entry is not None:
        return entry.slug
    return None


def resolve_effective_mcp_server_ids(
    db_session: Session,
    user: User,
    *,
    selected_mcp_server_ids: Sequence[int] | None = None,
    selected_skill_ids: Sequence[str] | None = None,
) -> list[int]:
    """Servers this turn may call: selected IDs plus skill-declared slugs.

    An empty selection (no IDs and no skills) returns no servers. Persona MCP
    tools are not implied. Only servers the user can access and authenticate
    are returned.
    """
    selected_ids = {int(server_id) for server_id in (selected_mcp_server_ids or ())}
    wanted_slugs: set[str] = set()
    for skill_id in selected_skill_ids or ():
        spec = load_skill_mcp_spec(skill_id)
        if spec is None:
            continue
        wanted_slugs.update(slugs_for_skill_spec(spec))

    if not selected_ids and not wanted_slugs:
        return []

    accessible = get_mcp_servers_accessible_to_user(
        user, db_session, include_system=True
    )
    user_configs = get_user_connection_configs(
        [server.id for server in accessible], user.email, db_session
    )
    slug_to_id: dict[str, int] = {}
    allowed: set[int] = set()
    for server in accessible:
        if not user_can_authenticate(
            server, user, db_session, user_configs=user_configs
        ):
            continue
        slug = catalog_slug_for_server(server)
        if slug:
            slug_to_id[slug] = server.id
        if server.id in selected_ids:
            allowed.add(server.id)
        if slug and slug in wanted_slugs:
            allowed.add(server.id)

    return sorted(allowed)


def get_mcp_servers_by_catalog_slugs(
    db_session: Session, slugs: Collection[str]
) -> list[MCPServer]:
    if not slugs:
        return []
    return list(
        db_session.scalars(
            select(MCPServer)
            .join(MCPCatalogEntry, MCPServer.catalog_entry_id == MCPCatalogEntry.id)
            .where(MCPCatalogEntry.slug.in_(list(slugs)))
        ).all()
    )
