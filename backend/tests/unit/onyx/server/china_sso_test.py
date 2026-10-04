"""Unit tests for China SSO: URL builders, code exchanges (mocked HTTP),
config models, and the identity email fallback."""

import httpx
import pytest
from pydantic import ValidationError

from onyx.db.enums import SSOProviderType
from onyx.db.sso_provider import (
    DingTalkProviderConfig,
    FeishuProviderConfig,
    WeComProviderConfig,
    WPS365ProviderConfig,
)
from onyx.server.china_sso import (
    ChinaSsoError,
    dingtalk_authorize_url,
    dingtalk_exchange,
    feishu_authorize_url,
    feishu_exchange,
    wecom_authorize_url,
    wecom_exchange,
    wps365_authorize_url,
    wps365_exchange,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


WECOM = WeComProviderConfig(
    corp_id="ww123",
    corp_secret="s3cret",
    agent_id="1000002",
    email_domain="corp.example.cn",
)
DINGTALK = DingTalkProviderConfig(
    client_id="ding-key", client_secret="ding-secret", email_domain="corp.example.cn"
)
FEISHU = FeishuProviderConfig(
    app_id="cli_a1", app_secret="fs-secret", email_domain="corp.example.cn"
)
WPS = WPS365ProviderConfig(
    client_id="wps-key", client_secret="wps-secret", email_domain="corp.example.cn"
)


def test_authorize_urls_contain_required_params() -> None:
    state = "st-123"
    redirect = "https://onyx.corp.example.cn/api/auth/china/callback"

    wecom_url = wecom_authorize_url(WECOM, state, redirect)
    assert "login.work.weixin.qq.com" in wecom_url
    assert "ww123" in wecom_url and "1000002" in wecom_url
    assert state in wecom_url

    ding_url = dingtalk_authorize_url(DINGTALK, state, redirect)
    assert "login.dingtalk.com/oauth2/auth" in ding_url
    assert "ding-key" in ding_url and "scope=openid" in ding_url

    feishu_url = feishu_authorize_url(FEISHU, state, redirect)
    assert "passport.feishu.cn" in feishu_url and "cli_a1" in feishu_url
    assert "scope=contact%3Auser.base%3Areadonly+contact%3Auser.email%3Areadonly" in (
        feishu_url
    )

    wps_url = wps365_authorize_url(WPS, state, redirect)
    assert "account.wps.cn/oauth2/v3/authorize" in wps_url


@pytest.mark.anyio
async def test_wecom_exchange_maps_departments() -> None:
    seen: list[httpx.Request] = []

    def route(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if "gettoken" in str(request.url):
            return httpx.Response(200, json={"errcode": 0, "access_token": "ct"})
        if "auth/getuserinfo" in str(request.url):
            return httpx.Response(200, json={"errcode": 0, "userid": "zhang"})
        if "user/get" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "errcode": 0,
                    "name": "张三",
                    "department": [2, 3],
                    "email": "zhang@corp.example.cn",
                },
            )
        if "department/list" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "errcode": 0,
                    "department": [
                        {"id": 1, "name": "总部"},
                        {"id": 2, "name": "财务部"},
                        {"id": 3, "name": "税务组"},
                    ],
                },
            )
        return httpx.Response(500)

    transport = httpx.MockTransport(route)
    async with httpx.AsyncClient(transport=transport) as client:
        identity = await wecom_exchange(client, WECOM, "auth-code")

    assert identity.account_id == "wecom:ww123:zhang"
    assert identity.email == "zhang@corp.example.cn"
    assert identity.display_name == "张三"
    assert set(identity.departments) == {"财务部", "税务组"}


@pytest.mark.anyio
async def test_wecom_exchange_error_raises() -> None:
    def route(request: httpx.Request) -> httpx.Response:
        if "gettoken" in str(request.url):
            return httpx.Response(200, json={"errcode": 40001, "errmsg": "bad secret"})
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(route)) as client:
        with pytest.raises(ChinaSsoError, match="bad secret"):
            await wecom_exchange(client, WECOM, "code")


@pytest.mark.anyio
async def test_dingtalk_exchange_builds_fallback_email() -> None:
    def route(request: httpx.Request) -> httpx.Response:
        if "userAccessToken" in str(request.url):
            assert request.headers["content-type"].startswith("application/json")
            return httpx.Response(200, json={"accessToken": "dt-token"})
        if "users/me" in str(request.url):
            return httpx.Response(
                200,
                json={"unionId": "union-9", "nick": "李四"},  # no email
            )
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(route)) as client:
        identity = await dingtalk_exchange(client, DINGTALK, "code")

    assert identity.account_id == "dingtalk:ding-key:union-9"
    assert identity.email == "union-9@corp.example.cn"
    assert identity.display_name == "李四"


@pytest.mark.anyio
async def test_feishu_exchange_prefers_real_email() -> None:
    def route(request: httpx.Request) -> httpx.Response:
        if "/oauth/token" in str(request.url):
            return httpx.Response(200, json={"access_token": "fs-token"})
        if "/oauth/userinfo" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "union_id": "ou_7",
                    "email": "wang@corp.example.cn",
                    "name": "王五",
                },
            )
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(route)) as client:
        identity = await feishu_exchange(client, FEISHU, "code")

    assert identity.account_id == "feishu:cli_a1:ou_7"
    assert identity.email == "wang@corp.example.cn"
    assert identity.display_name == "王五"


@pytest.mark.anyio
async def test_wps365_exchange_uses_configured_base() -> None:
    config = WPS.model_copy(update={"base_url": "https://account.wps.com"})

    def route(request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith("https://account.wps.com/")
        if "/oauth2/v3/token" in str(request.url):
            return httpx.Response(200, json={"access_token": "wps-token"})
        if "/oauth2/v3/userinfo" in str(request.url):
            return httpx.Response(
                200, json={"sub": "sub-1", "email": "u@corp.example.cn"}
            )
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(route)) as client:
        identity = await wps365_exchange(client, config, "code")

    assert identity.account_id == "wps365:wps-key:sub-1"
    assert identity.email == "u@corp.example.cn"


def test_config_models_reject_unknown_keys_and_hide_secrets() -> None:
    # unknown key → loud failure on write
    with pytest.raises(ValidationError):
        WeComProviderConfig.model_validate(
            {
                "corp_id": "a",
                "corp_secret": "b",
                "agent_id": "c",
                "email_domain": "d",
                "typo": 1,
            }
        )
    # secret marking present for admin serialization
    secret_fields = {
        name
        for name, field in WeComProviderConfig.model_fields.items()
        if (field.json_schema_extra or {}).get("secret")
    }
    assert secret_fields == {"corp_secret", "bot_encoding_aes_key"}
    # email_domain is required (identity stability)
    with pytest.raises(ValidationError):
        DingTalkProviderConfig.model_validate({"client_id": "a", "client_secret": "b"})


def test_china_types_in_provider_type_enum() -> None:
    from onyx.db.sso_provider import _CONFIG_MODEL_BY_TYPE

    for ptype in (
        SSOProviderType.WECOM,
        SSOProviderType.DINGTALK,
        SSOProviderType.FEISHU,
        SSOProviderType.WPS365,
    ):
        assert ptype in _CONFIG_MODEL_BY_TYPE


@pytest.mark.anyio
async def test_dingtalk_exchange_maps_departments() -> None:
    def route(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "oauth2/userAccessToken" in url:
            return httpx.Response(200, json={"accessToken": "ut"})
        if "contact/users/me" in url:
            return httpx.Response(
                200,
                json={
                    "unionId": "u-zhang",
                    "nick": "张三",
                    "email": "zhang@corp.example.cn",
                },
            )
        if "oauth2/accessToken" in url:
            return httpx.Response(200, json={"accessToken": "ct"})
        if "user/getByUnionid" in url:
            return httpx.Response(
                200, json={"errcode": 0, "result": {"userid": "u123"}}
            )
        if "topapi/v2/user/get" in url:
            return httpx.Response(
                200, json={"errcode": 0, "result": {"dept_id_list": [10, 20]}}
            )
        if "v2/department/listsub" in url:
            return httpx.Response(
                200,
                json={
                    "errcode": 0,
                    "result": [
                        {"dept_id": 10, "name": "研发部"},
                        {"dept_id": 20, "name": "生物医药组"},
                    ],
                },
            )
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(route)) as client:
        identity = await dingtalk_exchange(client, DINGTALK, "auth-code")

    assert identity.email == "zhang@corp.example.cn"
    assert set(identity.departments) == {"研发部", "生物医药组"}


@pytest.mark.anyio
async def test_dingtalk_department_failure_degrades_to_empty() -> None:
    def route(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "oauth2/userAccessToken" in url:
            return httpx.Response(200, json={"accessToken": "ut"})
        if "contact/users/me" in url:
            return httpx.Response(200, json={"unionId": "u-li"})
        # Contact APIs unavailable → login still succeeds, no departments.
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(route)) as client:
        identity = await dingtalk_exchange(client, DINGTALK, "auth-code")

    assert identity.departments == ()


@pytest.mark.anyio
async def test_feishu_exchange_maps_departments() -> None:
    def route(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "passport/oauth/token" in url:
            return httpx.Response(200, json={"access_token": "ut"})
        if "passport/oauth/userinfo" in url:
            return httpx.Response(
                200,
                json={
                    "union_id": "ou_zhang",
                    "name": "张三",
                    "email": "zhang@corp.example.cn",
                },
            )
        if "tenant_access_token/internal" in url:
            return httpx.Response(200, json={"code": 0, "tenant_access_token": "tt"})
        if "users/batch_get" in url:
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "users": [{"open_id": "ou_zhang", "department_ids": ["od-1"]}]
                    },
                },
            )
        if "contact/v3/departments/od-1" in url:
            return httpx.Response(
                200, json={"code": 0, "data": {"department": {"name": "财税风控部"}}}
            )
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(route)) as client:
        identity = await feishu_exchange(client, FEISHU, "auth-code")

    assert identity.email == "zhang@corp.example.cn"
    assert identity.departments == ("财税风控部",)
