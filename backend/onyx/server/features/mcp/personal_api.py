"""User-owned personal MCP servers. Isolated to the owner. Never uses Gateway."""

from __future__ import annotations

import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from onyx.auth.permission_projection import mcp_server_permissions, tool_permissions
from onyx.auth.permissions import require_permission
from onyx.configs.app_configs import PERSONAL_MCP_MAX_SERVERS
from onyx.db.engine.sql_engine import get_session
from onyx.db.enums import (
    MCPServerScope,
    MCPServerStatus,
    Permission,
)
from onyx.db.mcp import (
    affected_user_ids_for_mcp_server,
    count_personal_mcp_servers,
    delete_mcp_server,
    get_mcp_server_by_id,
    get_personal_mcp_servers,
    update_mcp_server__no_commit,
)
from onyx.db.models import User
from onyx.db.tools import (
    can_manage_mcp_server,
    can_manage_tool,
    get_tools_by_mcp_server_id,
)
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.server.features.mcp.api import (
    ToolSnapshotSource,
    _apply_mcp_server_access,
    _db_mcp_server_to_api_mcp_server,
    _hot_reload_craft_sessions,
    _list_mcp_tools_by_id,
    _sync_tools_for_server,
    _upsert_mcp_server,
)
from onyx.server.features.mcp.credentials import requires_user_authentication
from onyx.server.features.mcp.models import (
    MCPServer,
    MCPServerCreateResponse,
    MCPServerSimpleCreateRequest,
    MCPServerSimpleUpdateRequest,
    MCPServersResponse,
    MCPServerUpdateResponse,
    MCPToolCreateRequest,
    MCPToolUpdateRequest,
)
from onyx.server.features.tool.api import (
    ToolStatusUpdateRequest,
    ToolStatusUpdateResponse,
)
from onyx.server.features.tool.models import ToolSnapshot
from onyx.server.settings.store import load_settings
from onyx.utils.logger import setup_logger

logger = setup_logger()

personal_router = APIRouter(prefix="/mcp/personal")
_BASIC = require_permission(Permission.BASIC_ACCESS)


def _require_personal_enabled() -> None:
    if not load_settings().personal_mcp_enabled:
        raise OnyxError(
            OnyxErrorCode.FEATURE_NOT_AVAILABLE,
            "Personal MCP is turned off for this workspace.",
        )


def _personal_server_or_404(server_id: int, user: User, db: Session):
    try:
        server = get_mcp_server_by_id(server_id, db)
    except ValueError:
        raise HTTPException(status_code=404, detail="MCP server not found")
    if server.scope != MCPServerScope.PERSONAL or server.owner != user.email:
        raise HTTPException(status_code=404, detail="MCP server not found")
    return server


@personal_router.get("/servers")
def list_personal_servers(
    db: Session = Depends(get_session),
    user: User = Depends(_BASIC),
) -> MCPServersResponse:
    _require_personal_enabled()
    servers = get_personal_mcp_servers(db, user.email)
    return MCPServersResponse(
        mcp_servers=[
            _db_mcp_server_to_api_mcp_server(
                server,
                db,
                request_user=user,
                include_auth_config=True,
                permissions=mcp_server_permissions(
                    can_manage=can_manage_mcp_server(user, server)
                ),
            )
            for server in servers
        ]
    )


@personal_router.get("/servers/{server_id}")
def get_personal_server(
    server_id: int,
    db: Session = Depends(get_session),
    user: User = Depends(_BASIC),
) -> MCPServer:
    _require_personal_enabled()
    server = _personal_server_or_404(server_id, user, db)
    return _db_mcp_server_to_api_mcp_server(
        server,
        db,
        request_user=user,
        include_auth_config=True,
        permissions=mcp_server_permissions(can_manage=True),
    )


@personal_router.post("/server")
def create_personal_server_simple(
    request: MCPServerSimpleCreateRequest,
    db: Session = Depends(get_session),
    user: User = Depends(_BASIC),
) -> MCPServer:
    from onyx.db.mcp import create_mcp_server__no_commit
    from onyx.server.features.mcp.api import _validate_mcp_server_url

    _require_personal_enabled()
    if count_personal_mcp_servers(db, user.email) >= PERSONAL_MCP_MAX_SERVERS:
        raise OnyxError(
            OnyxErrorCode.INVALID_INPUT,
            f"You can create at most {PERSONAL_MCP_MAX_SERVERS} personal MCP servers.",
        )
    _validate_mcp_server_url(request.server_url, "server_url", require_https=False)
    server = create_mcp_server__no_commit(
        owner_email=user.email,
        name=request.name,
        description=request.description,
        server_url=request.server_url,
        auth_type=None,
        transport=None,
        auth_performer=None,
        db_session=db,
        is_public=False,
        scope=MCPServerScope.PERSONAL,
        available_in_craft=True,
    )
    _apply_mcp_server_access(
        mcp_server=server,
        acting_user=user,
        is_public=False,
        user_ids=[],
        group_ids=[],
        is_new=True,
        db_session=db,
    )
    db.commit()
    return _db_mcp_server_to_api_mcp_server(
        server,
        db,
        request_user=user,
        permissions=mcp_server_permissions(can_manage=True),
    )


@personal_router.patch("/server/{server_id}")
def update_personal_server_simple(
    server_id: int,
    request: MCPServerSimpleUpdateRequest,
    db: Session = Depends(get_session),
    user: User = Depends(_BASIC),
) -> MCPServer:
    from onyx.server.features.mcp.api import _validate_mcp_server_url

    _require_personal_enabled()
    server = _personal_server_or_404(server_id, user, db)
    _validate_mcp_server_url(request.server_url, "server_url", require_https=False)
    updated = update_mcp_server__no_commit(
        server_id=server_id,
        db_session=db,
        name=request.name,
        description=request.description,
        server_url=request.server_url,
        available_in_craft=True,
    )
    db.commit()
    _hot_reload_craft_sessions(affected_user_ids_for_mcp_server(updated, db), db)
    return _db_mcp_server_to_api_mcp_server(
        updated,
        db,
        request_user=user,
        permissions=mcp_server_permissions(can_manage=True),
    )


@personal_router.delete("/server/{server_id}")
def delete_personal_server(
    server_id: int,
    db: Session = Depends(get_session),
    user: User = Depends(_BASIC),
) -> dict[str, bool]:
    _require_personal_enabled()
    server = _personal_server_or_404(server_id, user, db)
    reload_ids = affected_user_ids_for_mcp_server(server, db)
    delete_mcp_server(server_id, db)
    db.commit()
    _hot_reload_craft_sessions(reload_ids, db)
    return {"success": True}


@personal_router.post("/servers/create")
def upsert_personal_server(
    request: MCPToolCreateRequest,
    db: Session = Depends(get_session),
    user: User = Depends(_BASIC),
) -> MCPServerCreateResponse:
    _require_personal_enabled()
    if request.gateway_binding is not None:
        raise OnyxError(
            OnyxErrorCode.INVALID_INPUT,
            "Personal MCP servers cannot use the gateway.",
        )
    request.is_public = False
    request.groups = []
    request.users = []
    if request.existing_server_id is None:
        if count_personal_mcp_servers(db, user.email) >= PERSONAL_MCP_MAX_SERVERS:
            raise OnyxError(
                OnyxErrorCode.INVALID_INPUT,
                f"You can create at most {PERSONAL_MCP_MAX_SERVERS} personal MCP servers.",
            )
    server = _upsert_mcp_server(
        request,
        db,
        user,
        scope=MCPServerScope.PERSONAL,
        available_in_craft=True,
    )
    if server.auth_type is None:
        raise HTTPException(
            status_code=500, detail="MCP server auth_type not configured"
        )
    return MCPServerCreateResponse(
        server_id=server.id,
        server_name=server.name,
        server_url=server.server_url,
        auth_type=server.auth_type.value,
        auth_performer=request.auth_performer.value if request.auth_performer else None,
        oauth_provider_mode=server.oauth_provider_mode,
        oauth_authorization_endpoint=server.oauth_authorization_endpoint,
        oauth_token_endpoint=server.oauth_token_endpoint,
        oauth_scopes_override=server.oauth_scopes_override,
        oauth_additional_auth_params=server.oauth_additional_auth_params,
        no_user_authentication_required=not requires_user_authentication(
            server.auth_type, request.auth_performer
        ),
    )


@personal_router.post("/servers/update")
def update_personal_server_tools(
    request: MCPToolUpdateRequest,
    db: Session = Depends(get_session),
    user: User = Depends(_BASIC),
) -> MCPServerUpdateResponse:
    _require_personal_enabled()
    server = _personal_server_or_404(request.server_id, user, db)
    if request.name is not None or request.description is not None:
        server = update_mcp_server__no_commit(
            server_id=server.id,
            db_session=db,
            name=request.name,
            description=request.description,
        )
    updated_tools = _sync_tools_for_server(
        server, set(request.selected_tools or []), db
    )
    db.commit()
    return MCPServerUpdateResponse(
        server_id=server.id,
        server_name=server.name,
        updated_tools=updated_tools,
    )


@personal_router.patch("/server/{server_id}/status")
def update_personal_server_status(
    server_id: int,
    status: MCPServerStatus,
    db: Session = Depends(get_session),
    user: User = Depends(_BASIC),
) -> None:
    _require_personal_enabled()
    _personal_server_or_404(server_id, user, db)
    update_mcp_server__no_commit(server_id=server_id, db_session=db, status=status)
    db.commit()


@personal_router.get("/server/{server_id}/tools")
def list_personal_tools(
    server_id: int,
    db: Session = Depends(get_session),
    user: User = Depends(_BASIC),
):
    _require_personal_enabled()
    _personal_server_or_404(server_id, user, db)
    return _list_mcp_tools_by_id(server_id, db, False, user)


@personal_router.get("/server/{server_id}/tools/snapshots")
def personal_tools_snapshots(
    server_id: int,
    source: ToolSnapshotSource = ToolSnapshotSource.DB,
    db: Session = Depends(get_session),
    user: User = Depends(_BASIC),
) -> list[ToolSnapshot]:
    _require_personal_enabled()
    server = _personal_server_or_404(server_id, user, db)
    if source == ToolSnapshotSource.MCP:
        try:
            _list_mcp_tools_by_id(server_id, db, False, user)
            update_mcp_server__no_commit(
                server_id=server_id,
                db_session=db,
                status=MCPServerStatus.CONNECTED,
                last_refreshed_at=datetime.datetime.now(datetime.timezone.utc),
            )
            db.commit()
        except Exception as error:
            update_mcp_server__no_commit(
                server_id=server_id,
                db_session=db,
                status=MCPServerStatus.AWAITING_AUTH,
            )
            db.commit()
            if isinstance(error, (HTTPException, OnyxError)):
                raise
            raise HTTPException(status_code=500, detail="Failed to discover tools")
    tools = get_tools_by_mcp_server_id(server_id, db, order_by_id=True)
    return [
        ToolSnapshot.from_model(
            tool, permissions=tool_permissions(can_manage=can_manage_tool(user, tool))
        )
        for tool in tools
    ]


@personal_router.patch("/tools/status")
def update_personal_tools_status(
    update_data: ToolStatusUpdateRequest,
    db: Session = Depends(get_session),
    user: User = Depends(_BASIC),
) -> ToolStatusUpdateResponse:
    _require_personal_enabled()
    from onyx.db.tools import get_tools_by_ids

    if not update_data.tool_ids:
        raise HTTPException(status_code=400, detail="No tool IDs provided")
    tools = get_tools_by_ids(update_data.tool_ids, db)
    updated: list[int] = []
    for tool in tools:
        server = tool.mcp_server
        if (
            server is None
            or server.scope != MCPServerScope.PERSONAL
            or server.owner != user.email
        ):
            raise HTTPException(status_code=404, detail="MCP server not found")
        tool.enabled = update_data.enabled
        updated.append(tool.id)
    db.commit()
    return ToolStatusUpdateResponse(updated_count=len(updated), tool_ids=updated)
