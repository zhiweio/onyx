import asyncio
from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import RequestResponseEndpoint
from starlette.types import Receive, Scope, Send

from onyx.configs.app_configs import MCP_GATEWAY_INTERNAL_TOKEN
from onyx.db.engine.sql_engine import SqlEngine, get_session_with_current_tenant
from onyx.db.mcp_gateway import list_providers
from onyx.error_handling.exceptions import register_onyx_exception_handlers
from onyx.mcp_gateway.protocol import (
    ProviderASGIApp,
    build_session_manager,
    run_session_managers,
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


def _ensure_provider_app(slug: str) -> ProviderASGIApp:
    existing = _apps.get(slug)
    if existing is not None:
        return existing
    manager = build_session_manager(slug)
    app = ProviderASGIApp(slug, manager)
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
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            return
        path = str(scope.get("path") or "")
        parts = [part for part in path.split("/") if part]
        if not parts or parts[0] != "p" or len(parts) < 2:
            response = JSONResponse({"error": "not_found"}, status_code=404)
            await response(scope, receive, send)
            return
        slug = parts[1]
        rest = "/" + "/".join(parts[2:]) if len(parts) > 2 else "/"
        new_scope = dict(scope)
        new_scope["path"] = rest or "/"
        new_scope["root_path"] = f"/p/{slug}"
        await _ensure_provider_running(slug)
        await _apps[slug](new_scope, receive, send)


def create_gateway_fastapi_app() -> FastAPI:
    dispatch = _ProviderDispatch()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
        global _stack
        logger.info("MCP gateway starting")
        SqlEngine.init_engine(pool_size=10, max_overflow=5)
        slugs: list[str] = []
        try:
            with get_session_with_current_tenant() as db_session:
                slugs = [item.slug for item in list_providers(db_session, enabled_only=True)]
        except Exception:
            logger.exception("Could not load gateway providers at startup")
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
        description="Cached commercial MCP proxy",
        version="1.0.0",
        lifespan=lifespan,
    )
    register_onyx_exception_handlers(app)

    @app.middleware("http")
    async def auth_and_health(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.url.path.rstrip("/") == "/health":
            return JSONResponse({"status": "healthy", "service": "mcp_gateway"})
        if MCP_GATEWAY_INTERNAL_TOKEN:
            auth = request.headers.get("authorization") or ""
            expected = f"Bearer {MCP_GATEWAY_INTERNAL_TOKEN}"
            if auth != expected and auth != MCP_GATEWAY_INTERNAL_TOKEN:
                return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)

    expose_prometheus_metrics(app, create_prometheus_instrumentator())
    app.mount("/", dispatch)
    return app


mcp_gateway_app = create_gateway_fastapi_app()
