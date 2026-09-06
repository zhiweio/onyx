"""System MCP catalog: admin-installed servers and who may use them.

Two layers, deliberately separate:

- **Access** is decided by the admin. An entry is either public to the whole
  organization or granted to specific user groups. There is no per-user grant —
  membership is the unit, which keeps a growing organization from turning into
  a per-user access matrix.
- **Enablement** is decided by the user. A grant makes a server available; a
  row in `mcp_user_enablement` means the user actually turned it on. No row
  means off, so widening a grant never silently adds tools to someone's chat.

Both layers sit behind the module toggle: when the gateway is off, no system
server is visible to anyone.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import Select, delete, select
from sqlalchemy.orm import Session, aliased
from sqlalchemy.orm.attributes import flag_modified

from onyx.auth.permissions import has_global_permission
from onyx.db.enums import (
    MCPCatalogOrigin,
    MCPGatewayAuthAdapter,
    MCPTransport,
    Permission,
)
from onyx.db.models import (
    MCPCatalogEntry,
    MCPCatalogEntry__UserGroup,
    MCPServer,
    MCPUserEnablement,
    User,
    User__UserGroup,
)
from onyx.utils.logger import setup_logger

logger = setup_logger()


# ---------------------------------------------------------------------------
# Catalog CRUD (admin side)
# ---------------------------------------------------------------------------


def get_catalog_entry_by_id(db_session: Session, entry_id: int) -> MCPCatalogEntry:
    entry = db_session.scalar(
        select(MCPCatalogEntry).where(MCPCatalogEntry.id == entry_id)
    )
    if entry is None:
        raise ValueError(f"MCP catalog entry {entry_id} does not exist")
    return entry


def get_catalog_entry_by_slug(db_session: Session, slug: str) -> MCPCatalogEntry | None:
    return db_session.scalar(
        select(MCPCatalogEntry).where(MCPCatalogEntry.slug == slug)
    )


def list_catalog_entries(
    db_session: Session, enabled_only: bool = False
) -> list[MCPCatalogEntry]:
    stmt = select(MCPCatalogEntry).order_by(MCPCatalogEntry.display_name)
    if enabled_only:
        stmt = stmt.where(MCPCatalogEntry.enabled.is_(True))
    return list(db_session.scalars(stmt).all())


def create_catalog_entry__no_commit(
    db_session: Session,
    *,
    slug: str,
    display_name: str,
    description: str | None,
    upstream_url: str,
    transport: MCPTransport,
    auth_adapter: MCPGatewayAuthAdapter,
    credentials: dict[str, Any],
    pack_slug: str,
    policy_overrides: dict[str, Any] | None = None,
    enabled: bool = True,
    is_public: bool = False,
    origin: MCPCatalogOrigin = MCPCatalogOrigin.LOCAL,
) -> MCPCatalogEntry:
    entry = MCPCatalogEntry(
        slug=slug,
        display_name=display_name,
        description=description,
        upstream_url=upstream_url,
        transport=transport,
        auth_adapter=auth_adapter,
        credentials=credentials,
        pack_slug=pack_slug,
        policy_overrides=policy_overrides,
        enabled=enabled,
        is_public=is_public,
        origin=origin,
    )
    db_session.add(entry)
    db_session.flush()
    return entry


def update_catalog_entry__no_commit(
    db_session: Session,
    entry: MCPCatalogEntry,
    *,
    display_name: str | None = None,
    description: str | None = None,
    upstream_url: str | None = None,
    transport: MCPTransport | None = None,
    auth_adapter: MCPGatewayAuthAdapter | None = None,
    credentials: dict[str, Any] | None = None,
    pack_slug: str | None = None,
    policy_overrides: dict[str, Any] | None = None,
    enabled: bool | None = None,
    is_public: bool | None = None,
) -> MCPCatalogEntry:
    if display_name is not None:
        entry.display_name = display_name
    if description is not None:
        entry.description = description
    if upstream_url is not None:
        entry.upstream_url = upstream_url
    if transport is not None:
        entry.transport = transport
    if auth_adapter is not None:
        entry.auth_adapter = auth_adapter
    if credentials is not None:
        entry.credentials = credentials  # ty: ignore[invalid-assignment]
        flag_modified(entry, "credentials")
    if pack_slug is not None:
        entry.pack_slug = pack_slug
    if policy_overrides is not None:
        entry.policy_overrides = policy_overrides
    if enabled is not None:
        entry.enabled = enabled
    if is_public is not None:
        entry.is_public = is_public
    db_session.flush()
    return entry


def delete_catalog_entry__no_commit(
    db_session: Session, entry: MCPCatalogEntry
) -> None:
    """Delete an entry without owning the transaction.

    Callers that keep a projected MCPServer must null ``catalog_entry_id``
    first. The FK cascades and would otherwise delete the server.
    """
    db_session.delete(entry)
    db_session.flush()


def delete_catalog_entry(db_session: Session, entry: MCPCatalogEntry) -> None:
    """Delete an entry. The projected MCPServer and its tools cascade."""
    delete_catalog_entry__no_commit(db_session, entry)
    db_session.commit()


def set_catalog_entry_groups__no_commit(
    db_session: Session, entry_id: int, group_ids: list[int]
) -> None:
    """Replace the set of groups an entry is granted to."""
    db_session.execute(
        delete(MCPCatalogEntry__UserGroup).where(
            MCPCatalogEntry__UserGroup.catalog_entry_id == entry_id
        )
    )
    if group_ids:
        db_session.add_all(
            [
                MCPCatalogEntry__UserGroup(
                    catalog_entry_id=entry_id, user_group_id=group_id
                )
                for group_id in set(group_ids)
            ]
        )
    db_session.flush()


def get_catalog_entry_group_ids(db_session: Session, entry_id: int) -> list[int]:
    return list(
        db_session.scalars(
            select(MCPCatalogEntry__UserGroup.user_group_id).where(
                MCPCatalogEntry__UserGroup.catalog_entry_id == entry_id
            )
        ).all()
    )


# ---------------------------------------------------------------------------
# Access filter (user side)
# ---------------------------------------------------------------------------


def add_catalog_access_filter(stmt: Select, user: User | None) -> Select:
    """Narrow a `MCPCatalogEntry` query to what `user` has been granted.

    Admins and MANAGE_SYSTEM_MCP holders bypass the grant check so they can see
    what they installed before granting it to anyone. Everyone else sees public
    entries plus those granted to a group they belong to.
    """
    stmt = stmt.where(MCPCatalogEntry.enabled.is_(True))

    if user is not None and (
        has_global_permission(user, Permission.FULL_ADMIN_PANEL_ACCESS)
        or has_global_permission(user, Permission.MANAGE_SYSTEM_MCP)
    ):
        return stmt

    stmt = stmt.distinct()
    Entry__UG = aliased(MCPCatalogEntry__UserGroup)
    stmt = stmt.outerjoin(
        Entry__UG, Entry__UG.catalog_entry_id == MCPCatalogEntry.id
    ).outerjoin(
        User__UserGroup,
        User__UserGroup.user_group_id == Entry__UG.user_group_id,
    )

    where_clause = MCPCatalogEntry.is_public.is_(True)
    if user is not None and not user.is_anonymous:
        where_clause |= User__UserGroup.user_id == user.id
    return stmt.where(where_clause)


def list_catalog_entries_for_user(
    db_session: Session, user: User | None
) -> list[MCPCatalogEntry]:
    """Enabled entries `user` may use, in display order."""
    stmt = add_catalog_access_filter(
        select(MCPCatalogEntry).order_by(MCPCatalogEntry.display_name), user
    )
    return list(db_session.scalars(stmt).all())


def accessible_system_server_ids(db_session: Session, user: User | None) -> set[int]:
    """IDs of system MCP servers `user` has been granted, enabled or not."""
    stmt = add_catalog_access_filter(
        select(MCPServer.id).join(
            MCPCatalogEntry, MCPCatalogEntry.id == MCPServer.catalog_entry_id
        ),
        user,
    )
    return set(db_session.scalars(stmt).all())


def user_can_access_catalog_entry(
    db_session: Session, user: User | None, entry_id: int
) -> bool:
    stmt = add_catalog_access_filter(
        select(MCPCatalogEntry.id).where(MCPCatalogEntry.id == entry_id), user
    )
    return db_session.scalar(stmt) is not None


# ---------------------------------------------------------------------------
# Per-user enablement
# ---------------------------------------------------------------------------


def get_enabled_system_server_ids(db_session: Session, user_id: UUID) -> set[int]:
    """System servers this user switched on. Absence of a row means off."""
    return set(
        db_session.scalars(
            select(MCPUserEnablement.mcp_server_id).where(
                MCPUserEnablement.user_id == user_id,
                MCPUserEnablement.enabled.is_(True),
            )
        ).all()
    )


def set_system_server_enabled(
    db_session: Session, user_id: UUID, mcp_server_id: int, enabled: bool
) -> None:
    """Turn a system server on or off for one user."""
    row = db_session.scalar(
        select(MCPUserEnablement).where(
            MCPUserEnablement.user_id == user_id,
            MCPUserEnablement.mcp_server_id == mcp_server_id,
        )
    )
    if row is None:
        row = MCPUserEnablement(
            user_id=user_id, mcp_server_id=mcp_server_id, enabled=enabled
        )
        db_session.add(row)
    else:
        row.enabled = enabled
    db_session.commit()


def prune_enablements_for_lost_access(db_session: Session, user_id: UUID) -> int:
    """Drop enablement rows for servers the user can no longer reach.

    Access is re-checked at call time, so a stale row is not a hole. This keeps
    the settings page honest after a group change.
    """
    allowed = accessible_system_server_ids(db_session, db_session.get(User, user_id))
    stmt = delete(MCPUserEnablement).where(MCPUserEnablement.user_id == user_id)
    if allowed:
        stmt = stmt.where(MCPUserEnablement.mcp_server_id.notin_(allowed))
    result = db_session.execute(stmt)
    db_session.commit()
    return result.rowcount or 0  # ty: ignore[unresolved-attribute]
