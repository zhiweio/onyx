"""The gateway ASGI service.

Serves one MCP endpoint per catalog entry at `/p/{slug}`. Every request must
carry a token minted by the API server; the tenant comes from the verified
claims, and the slug in the token must match the path being called, so a token
for one system MCP cannot be replayed against another.
"""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import RequestResponseEndpoint
from starlette.types import Receive, Scope, Send

from onyx.db.engine.sql_engine import SqlEngine, get_session_with_current_tenant
from onyx.db.mcp_catalog import list_catalog_entries
from onyx.error_handling.exceptions import register_onyx_exception_handlers
from onyx.mcp_gateway.protocol import (
    TENANT_SCOPE_KEY,
    USER_EMAIL_SCOPE_KEY,
    ProviderASGIApp,
    build_session_manager,
    run_session_managers,
)
from onyx.mcp_gateway.tokens import (
    GatewayTokenError,
    gateway_signing_secret,
    verify_gateway_token,
)
from onyx.server.metrics.prometheus_setup import (
    create_prometheus_instrumentator,
    expose_prometheus_metrics,
)
from onyx.utils.logger import setup_logger
from onyx.utils.variable_functionality import set_is_ee_based_on_env_variable

logger = setup_logger()
set_is_ee_based_on_env_variable()

_apps: dict[str, ProviderASGIApp] = {}
_started_slugs: set[str] = set()
_stack: AsyncExitStack | None = None
_start_lock = asyncio.Lock()

_HEALTH_PATH = "/health"


def _ensure_provider_app(slug: str) -> ProviderASGIApp:
    existing = _apps.get(slug)
    if existing is not None:
        return existing
    app = ProviderASGIApp(slug, build_session_manager(slug))
    _apps[slug] = app
    return app


async def _ensure_provider_running(slug: str) -> ProviderASGIApp:
    app = _ensure_provider_app(slug)
    if slug in _started_slugs:
        return app
    async with _start_lock:
        if slug in _started_slugs:
            return app
        if _stack is not None:
            await _stack.enter_async_context(app.session_manager.run())
            _started_slugs.add(slug)
    return app


class _ProviderDispatch:
    """Route `/p/{slug}/...` to that entry's MCP server."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            return
        path = str(scope.get("path") or "")
        parts = [part for part in path.split("/") if part]
        if not parts or parts[0] != "p" or len(parts) < 2:
            await JSONResponse({"error": "not_found"}, status_code=404)(
                scope, receive, send
            )
            return

        slug = parts[1]
        # The middleware verified the token; the claim must name this entry.
        if scope.get("onyx_catalog_slug") != slug:
            await JSONResponse({"error": "forbidden"}, status_code=403)(
                scope, receive, send
            )
            return

        rest = "/" + "/".join(parts[2:]) if len(parts) > 2 else "/"
        child_scope = dict(scope)
        child_scope["path"] = rest or "/"
        child_scope["root_path"] = f"/p/{slug}"
        await _ensure_provider_running(slug)
        await _apps[slug](child_scope, receive, send)


def create_gateway_fastapi_app() -> FastAPI:
    dispatch = _ProviderDispatch()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
        global _stack
        logger.info("MCP gateway starting")
        if not gateway_signing_secret():
            # Without a secret nothing can be verified, so every request would
            # be rejected. Say so once at boot instead of per request.
            logger.error(
                "MCP_GATEWAY_INTERNAL_TOKEN is not set; the gateway will reject "
                "every request"
            )
        SqlEngine.init_engine(pool_size=10, max_overflow=5)
        try:
            from onyx.db.mcp_iceberg import ensure_mcp_iceberg_tables

            ensure_mcp_iceberg_tables()
        except Exception:
            logger.exception("Could not initialize MCP Iceberg tables")

        slugs: list[str] = []
        try:
            with get_session_with_current_tenant() as db_session:
                slugs = [
                    entry.slug
                    for entry in list_catalog_entries(db_session, enabled_only=True)
                ]
        except Exception:
            logger.exception("Could not load MCP catalog entries at startup")

        for slug in slugs:
            _ensure_provider_app(slug)

        managers = [app.session_manager for app in _apps.values()]
        async with AsyncExitStack() as stack:
            _stack = stack
            if managers:
                await stack.enter_async_context(run_session_managers(managers))
                _started_slugs.update(_apps.keys())
            yield
            _stack = None
            _started_slugs.clear()
        logger.info("MCP gateway stopped")

    app = FastAPI(
        title="Onyx MCP Gateway",
        description="Cached system MCP proxy",
        version="1.0.0",
        lifespan=lifespan,
    )
    register_onyx_exception_handlers(app)

    @app.middleware("http")
    async def authenticate(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.url.path.rstrip("/") == _HEALTH_PATH:
            return JSONResponse({"status": "healthy", "service": "mcp_gateway"})

        header = request.headers.get("authorization") or ""
        token = header[7:] if header.lower().startswith("bearer ") else header
        if not token:
            return JSONResponse({"error": "unauthorized"}, status_code=401)

        try:
            claims = verify_gateway_token(token)
        except GatewayTokenError as error:
            logger.warning("Rejected MCP gateway request: %s", error)
            return JSONResponse({"error": "unauthorized"}, status_code=401)

        # Tenant comes from the signed claims. A client-supplied
        # X-Onyx-Tenant-Id header is ignored on purpose.
        request.scope[TENANT_SCOPE_KEY] = claims.tenant_id
        request.scope["onyx_catalog_slug"] = claims.catalog_slug
        request.scope[USER_EMAIL_SCOPE_KEY] = claims.user_email
        return await call_next(request)

    expose_prometheus_metrics(app, create_prometheus_instrumentator())
    app.mount("/", dispatch)
    return app


mcp_gateway_app = create_gateway_fastapi_app()
