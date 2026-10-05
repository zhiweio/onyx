"""Org-level derived access tokens for egress credential injection.

Some providers (WeCom's CLI gateway) authenticate with an org credential that
must never ride on the wire: the gate derives a short-lived bearer token from
it, caches it fleet-wide in Redis, and merges it into the credential dict
before ``auth_template`` renders. Mirrors :mod:`onyx.external_apps.token_refresh`
in shape — short-lived Redis lock, no DB connection held across the token POST —
but the result is cached, never persisted to the ``external_app`` tables.
"""

import hashlib
import secrets
import time
from typing import Any, Callable

import requests
from redis.exceptions import RedisError

from onyx.external_apps.providers.base import OrgTokenSpec
from onyx.redis.lock_context import RedisSharedLockAcquisitionError, redis_shared_lock
from onyx.redis.redis_pool import get_shared_redis_client
from onyx.utils.logger import setup_logger

logger = setup_logger()

# Held long enough for the token POST; short wait so a waiter doesn't pin a
# worker thread (a timed-out waiter re-reads the cache, then fails closed).
_LOCK_HELD_S = 20.0
_LOCK_WAIT_S = 3.0

_HTTP_TIMEOUT_SECONDS = 20.0
# Cache margin so a token near expiry isn't injected onto a slow request.
_TTL_MARGIN_S = 60
# WeCom's CLI token carries no expires_in; re-derive at this cadence. (The
# gateway answers errcode 853004/853005 for a dead token — the agent-visible
# retry costs one approval-free re-run, so err on the short side.)
_DEFAULT_TTL_S = 3000
_MAX_TTL_S = 7100
# A failed derivation parks retries briefly so a burst of requests doesn't
# hammer the token endpoint while credentials are broken.
_NEGATIVE_TTL_S = 60

# --- Request builders, one per OrgTokenSpec.kind -------------------------------

_WECOM_CLI_KIND = "wecom_cli"
_WECOM_CLI_TOKEN_URL = "https://qyapi.weixin.qq.com/cgi-bin/aibot/cli/get_cli_config"


def _build_wecom_cli_request(
    org_credentials: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """The WeCom CLI-gateway bootstrap: sha256(secret + bot_id + time + nonce)."""
    bot_id = str(org_credentials.get("bot_id") or "")
    bot_secret = str(org_credentials.get("bot_secret") or "")
    now = int(time.time())
    nonce = f"onyx_{int(time.time() * 1000)}_{secrets.token_hex(4)}"
    signature = hashlib.sha256(f"{bot_secret}{bot_id}{now}{nonce}".encode()).hexdigest()
    body = {
        "bot_id": bot_id,
        "time": now,
        "nonce": nonce,
        "signature": signature,
        "bind_source": 1,
    }
    return _WECOM_CLI_TOKEN_URL, body


_BUILDERS_BY_KIND: dict[str, Callable[[dict[str, Any]], tuple[str, dict[str, Any]]]] = {
    _WECOM_CLI_KIND: _build_wecom_cli_request,
}

# --- Fetch & cache ---------------------------------------------------------------


def _cache_ttl_seconds(raw: Any) -> int:
    """Honour the endpoint's ``expires_in`` when sane; clamp to the cap."""
    try:
        expires_in = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return _DEFAULT_TTL_S
    return max(60, min(expires_in, _MAX_TTL_S))


def _fetch_org_token(
    spec: OrgTokenSpec, org_credentials: dict[str, Any]
) -> tuple[str, int] | None:
    """One token POST: ``(token, cache_ttl_seconds)``, or ``None`` on any
    failure (logged; the caller decides how to surface it)."""
    builder = _BUILDERS_BY_KIND.get(spec.kind)
    if builder is None:
        logger.error("org_token.unknown_kind kind=%s", spec.kind)
        return None

    missing = [k for k in spec.credential_keys if not org_credentials.get(k)]
    if missing:
        logger.warning(
            "org_token.missing_credentials kind=%s missing=%s", spec.kind, missing
        )
        return None

    url, body = builder(org_credentials)
    try:
        response = requests.post(  # noqa: S113 — bounded below
            url, json=body, timeout=_HTTP_TIMEOUT_SECONDS
        )
    except requests.RequestException as exc:
        logger.warning("org_token.network_error kind=%s error=%r", spec.kind, exc)
        return None
    if response.status_code >= 400:
        logger.warning(
            "org_token.http_error kind=%s status=%s", spec.kind, response.status_code
        )
        return None
    try:
        payload = response.json()
    except ValueError:
        logger.warning("org_token.non_json_response kind=%s", spec.kind)
        return None
    if payload.get("errcode") not in (None, 0):
        logger.warning(
            "org_token.endpoint_error kind=%s errcode=%s",
            spec.kind,
            payload.get("errcode"),
        )
        return None
    token = payload.get("token")
    if not token:
        logger.warning("org_token.no_token_in_response kind=%s", spec.kind)
        return None
    ttl = _cache_ttl_seconds(payload.get("expires_in")) - _TTL_MARGIN_S
    return str(token), max(60, ttl)


def _cache_keys(tenant_id: str, external_app_id: int) -> tuple[str, str]:
    positive = f"ea_org_token:{tenant_id}:{external_app_id}"
    return positive, f"{positive}:fail"


def _read_cache(keys: tuple[str, str]) -> tuple[str | None, bool]:
    """``(cached_token, recently_failed)``; tolerant of Redis being down."""
    positive, negative = keys
    try:
        redis_client = get_shared_redis_client()
        cached = redis_client.get(positive)
        failed = redis_client.get(negative) is not None
        return (cached.decode() if isinstance(cached, bytes) else cached), failed
    except RedisError as exc:
        logger.warning("org_token.cache_unavailable error=%r", exc)
        return None, False


def _write_cache(
    keys: tuple[str, str], token: str | None, ttl_seconds: int | None
) -> None:
    positive, negative = keys
    try:
        redis_client = get_shared_redis_client()
        if token is not None and ttl_seconds is not None:
            redis_client.set(positive, token, ex=ttl_seconds)
            redis_client.delete(negative)
        else:
            redis_client.set(negative, "1", ex=_NEGATIVE_TTL_S)
    except RedisError as exc:
        logger.warning("org_token.cache_write_failed error=%r", exc)


def ensure_org_token(
    tenant_id: str,
    external_app_id: int,
    spec: OrgTokenSpec,
    org_credentials: dict[str, Any],
) -> str | None:
    """The cached org token for an app, deriving (and caching) it on miss.

    Single-flighted per ``(tenant, app)`` via a Redis lock. Returns ``None``
    when the derivation fails — broken credentials, endpoint error, or a
    recent failure — and the caller should fail the request closed.
    """
    keys = _cache_keys(tenant_id, external_app_id)
    cached, recently_failed = _read_cache(keys)
    if cached:
        return cached
    if recently_failed:
        return None

    lock_name = f"ea_org_token_fetch:{tenant_id}:{external_app_id}"
    try:
        with redis_shared_lock(
            lock_name,
            max_time_lock_held_s=_LOCK_HELD_S,
            wait_for_lock_s=_LOCK_WAIT_S,
            logger=logger,
        ):
            # Double-check after the lock wait: the winner may have cached it.
            cached, recently_failed = _read_cache(keys)
            if cached or recently_failed:
                return cached if not recently_failed else None

            fetched = _fetch_org_token(spec, org_credentials)
            if fetched is None:
                _write_cache(keys, None, None)
                return None
            token, ttl = fetched
            _write_cache(keys, token, ttl)
            return token
    except RedisSharedLockAcquisitionError:
        # The lock winner is fetching; don't fail the request on the race —
        # one more cache read, then let the caller decide.
        cached, _ = _read_cache(keys)
        if cached:
            return cached
        logger.info("org_token.lock_contended external_app_id=%s", external_app_id)
        return None
    except RedisError as exc:
        logger.warning("org_token.infra_unavailable error=%r", exc)
        # Redis is down; derive without caching so the request still works.
        fetched = _fetch_org_token(spec, org_credentials)
        return fetched[0] if fetched else None
