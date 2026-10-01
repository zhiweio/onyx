import functools
import importlib
import inspect
from typing import Any, TypeVar

from onyx.configs.app_configs import (
    API_SERVER_HOST,
    API_SERVER_PROTOCOL,
    API_SERVER_URL_OVERRIDE_FOR_HTTP_REQUESTS,
    APP_API_PREFIX,
    APP_PORT,
    DEV_MODE,
)
from onyx.utils.logger import setup_logger

logger = setup_logger()


class OnyxVersion:
    """This build ships Community Edition only; the Enterprise Edition package
    is physically absent. ``is_ee_version()`` is therefore a constant so the
    historical call sites keep compiling while the EE branches stay dead."""

    def is_ee_version(self) -> bool:
        return False


global_version = OnyxVersion()


def set_is_ee_based_on_env_variable() -> None:
    """Kept for backwards compatibility: EE can no longer be enabled by
    environment configuration in this CE-only build, so this is a no-op."""


@functools.lru_cache(maxsize=128)
def fetch_versioned_implementation(module: str, attribute: str) -> Any:
    """Fetch ``attribute`` from ``module``.

    Historically this resolved an ``ee.``-prefixed module first in Enterprise
    builds. This is a CE-only build, so the module name is used as given.

    Raises:
        ModuleNotFoundError: if the module does not exist.
        AttributeError: if the module exists but lacks the attribute.
    """
    logger.debug("Fetching versioned implementation for %s.%s", module, attribute)
    return getattr(  # ods: ignore[getattr]
        importlib.import_module(module), attribute
    )


T = TypeVar("T")


def fetch_versioned_implementation_with_fallback(
    module: str, attribute: str, fallback: T
) -> T:
    """Fetch ``attribute`` from ``module``, returning ``fallback`` on any failure.

    Kept because several optional integrations ride on the fallback instead of
    hard-importing their target module.
    """
    try:
        return fetch_versioned_implementation(module, attribute)
    except Exception:
        return fallback


def noop_fallback(*args: Any, **kwargs: Any) -> None:
    """Accept anything, do nothing — placeholder callback."""


def fetch_ee_implementation_or_noop(
    module: str,  # noqa: ARG001
    attribute: str,  # noqa: ARG001
    noop_return_value: Any = None,
) -> Any:
    """Always returns a no-op: the EE implementations these call sites used to
    reach do not exist in this CE-only build. Kept so ~76 call sites that guard
    optional enterprise hooks stay source-compatible."""
    if inspect.iscoroutinefunction(noop_return_value):

        async def async_noop(*args: Any, **kwargs: Any) -> Any:
            return await noop_return_value(*args, **kwargs)

        return async_noop

    def sync_noop(*args: Any, **kwargs: Any) -> Any:  # noqa: ARG001
        return noop_return_value

    return sync_noop


def build_api_server_url_for_http_requests(
    respect_env_override_if_set: bool = False,
) -> str:
    """
    Builds the API server URL for HTTP requests.
    """
    if DEV_MODE:
        url = f"http://127.0.0.1:{APP_PORT}"
    elif respect_env_override_if_set and API_SERVER_URL_OVERRIDE_FOR_HTTP_REQUESTS:
        url = API_SERVER_URL_OVERRIDE_FOR_HTTP_REQUESTS.rstrip("/")
    else:
        url = f"{API_SERVER_PROTOCOL}://{API_SERVER_HOST}:{APP_PORT}"

    if APP_API_PREFIX:
        url += f"/{APP_API_PREFIX.strip('/')}"

    return url
