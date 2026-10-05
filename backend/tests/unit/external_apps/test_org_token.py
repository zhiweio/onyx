"""Unit tests for the org-token derivation used by org-credential providers
(WeCom's CLI gateway): request signing, envelope parsing, Redis caching, and
fail-closed behaviour."""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from typing import Any

import pytest
import requests
from redis.exceptions import ConnectionError as RedisConnectionError

from onyx.external_apps import org_token as ot
from onyx.external_apps.providers.base import OrgTokenSpec

_SPEC = OrgTokenSpec(kind="wecom_cli", credential_keys=("bot_id", "bot_secret"))
_CREDS = {"bot_id": "BOT", "bot_secret": "SECRET"}


class _FakeRedis:
    """Just enough dict semantics for the org-token cache paths."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int | None] = {}

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.ttls[key] = ex
        self.store[key] = value

    def delete(self, key: str) -> None:
        self.store.pop(key, None)


class _BrokenRedis(_FakeRedis):
    def get(self, key: str) -> str | None:
        del key
        raise RedisConnectionError("down")

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        del key, value, ex
        raise RedisConnectionError("down")

    def delete(self, key: str) -> None:
        del key
        raise RedisConnectionError("down")


@pytest.fixture(autouse=True)
def _no_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    """The unit tests don't exercise locking — pass straight through."""

    @contextmanager
    def _passthrough(*_a: Any, **_k: Any):
        yield "lock"

    monkeypatch.setattr(ot, "redis_shared_lock", _passthrough)


def _install_redis(monkeypatch: pytest.MonkeyPatch, client: Any) -> _FakeRedis:
    monkeypatch.setattr(ot, "get_shared_redis_client", lambda: client)
    return client


def _response(status_code: int, body: dict[str, Any]) -> requests.Response:
    response = requests.Response()
    response.status_code = status_code
    response._content = json.dumps(body).encode()
    return response


def test_fetch_signs_bot_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def _post(url: str, json: dict[str, Any], timeout: float) -> requests.Response:
        del timeout
        captured["url"] = url
        captured["body"] = json
        return _response(200, {"errcode": 0, "token": "tok"})

    monkeypatch.setattr(ot.requests, "post", _post)
    _install_redis(monkeypatch, _FakeRedis())
    token = ot.ensure_org_token("t1", 1, _SPEC, _CREDS)

    assert token == "tok"
    assert captured["url"] == ot._WECOM_CLI_TOKEN_URL
    body = captured["body"]
    assert body["bot_id"] == "BOT"
    assert body["bind_source"] == 1
    expected = hashlib.sha256(
        f"SECRET{body['bot_id']}{body['time']}{body['nonce']}".encode()
    ).hexdigest()
    assert body["signature"] == expected


def test_fetch_caches_and_reuses(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def _post(*_a: Any, **_k: Any) -> requests.Response:
        calls["n"] += 1
        return _response(200, {"errcode": 0, "token": "tok"})

    monkeypatch.setattr(ot.requests, "post", _post)
    redis = _install_redis(monkeypatch, _FakeRedis())
    assert ot.ensure_org_token("t1", 1, _SPEC, _CREDS) == "tok"
    assert ot.ensure_org_token("t1", 1, _SPEC, _CREDS) == "tok"
    assert calls["n"] == 1
    # Cached under the tenant+app key, not the second tenant's.
    assert redis.store["ea_org_token:t1:1"] == "tok"
    assert ot.ensure_org_token("t2", 1, _SPEC, _CREDS) == "tok"
    assert calls["n"] == 2


def test_endpoint_error_fails_closed_with_negative_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"n": 0}

    def _post(*_a: Any, **_k: Any) -> requests.Response:
        calls["n"] += 1
        return _response(200, {"errcode": 60020, "errmsg": "not allowed"})

    monkeypatch.setattr(ot.requests, "post", _post)
    redis = _install_redis(monkeypatch, _FakeRedis())
    assert ot.ensure_org_token("t1", 1, _SPEC, _CREDS) is None
    # Negative cache: the retry inside the TTL window doesn't re-hit the API.
    assert ot.ensure_org_token("t1", 1, _SPEC, _CREDS) is None
    assert calls["n"] == 1
    assert "ea_org_token:t1:1:fail" in redis.store


def test_incomplete_credentials_fails_without_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _post(*_a: Any, **_k: Any) -> requests.Response:
        raise AssertionError("must not reach the network")

    monkeypatch.setattr(ot.requests, "post", _post)
    _install_redis(monkeypatch, _FakeRedis())
    assert ot.ensure_org_token("t1", 1, _SPEC, {"bot_id": "BOT"}) is None


def test_unknown_kind_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ot.requests, "post", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError())
    )
    _install_redis(monkeypatch, _FakeRedis())
    spec = OrgTokenSpec(kind="nope", credential_keys=("k",))
    assert ot.ensure_org_token("t1", 1, spec, {"k": "v"}) is None


def test_redis_down_still_derives(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def _post(*_a: Any, **_k: Any) -> requests.Response:
        calls["n"] += 1
        return _response(200, {"errcode": 0, "token": "tok"})

    monkeypatch.setattr(ot.requests, "post", _post)
    _install_redis(monkeypatch, _BrokenRedis())
    # No cache to serve or write → derive on each call.
    assert ot.ensure_org_token("t1", 1, _SPEC, _CREDS) == "tok"
    assert ot.ensure_org_token("t1", 1, _SPEC, _CREDS) == "tok"
    assert calls["n"] == 2


def test_expires_in_is_honoured_and_clamped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ot.requests,
        "post",
        lambda *_a, **_k: _response(
            200, {"errcode": 0, "token": "t", "expires_in": 99999}
        ),
    )
    ttl_box: dict[str, int | None] = {"ex": None}

    class _TtlRedis(_FakeRedis):
        def set(self, key: str, value: str, ex: int | None = None) -> None:
            ttl_box["ex"] = ex
            super().set(key, value, ex=ex)

    _install_redis(monkeypatch, _TtlRedis())
    assert ot.ensure_org_token("t1", 1, _SPEC, _CREDS) == "t"
    assert ttl_box["ex"] == ot._MAX_TTL_S - ot._TTL_MARGIN_S
