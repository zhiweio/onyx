"""China workplace SSO: WeCom / DingTalk / Feishu / WPS365 login.

All four provision through the standard OAuth machinery
(``UserManager.oauth_callback`` + ``complete_login_flow``) so users,
sessions and domain gates behave exactly like OIDC logins. What differs
per platform is the code exchange and identity fetch, implemented here
as small protocol functions instead of authlib clients (DingTalk's token
endpoint speaks JSON, WeCom needs a corp access token, Feishu is
near-standard OAuth2, WPS365 is standard OAuth2 on a regional base URL).

Identity emails: platforms that do not return an email get a
deterministic ``{account_id}@{email_domain}`` address, so one platform
identity always maps to one Onyx user.

Org sync: after a successful login the user's platform departments are
mapped onto Onyx user groups (best-effort, never blocks login). WeCom,
DingTalk, and Feishu read departments through their contact APIs; WPS365's
org structure has no stable open contact API, so it stays without
department sync (documented degradation in docs/mainland).
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Generator
from urllib.parse import quote_plus

import httpx
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from httpx_oauth.oauth2 import BaseOAuth2, OAuth2Token
from sqlalchemy.orm import Session

from onyx.auth.sso_tenant_token import SSO_TENANT_TOKEN_PARAM, decode_sso_tenant_token
from onyx.auth.users import (
    CSRF_TOKEN_COOKIE_NAME,
    CSRF_TOKEN_KEY,
    UserManager,
    auth_backend,
    complete_login_flow,
    decode_and_validate_oauth_state,
    generate_csrf_token,
    generate_state_token,
    get_user_manager,
)
from onyx.configs.app_configs import MULTI_TENANT, USER_AUTH_SECRET, WEB_DOMAIN
from onyx.db.engine.sql_engine import (
    get_session_with_current_tenant,
    get_session_with_tenant,
)
from onyx.db.enums import SSOProviderType
from onyx.db.models import SSOProvider
from onyx.db.sso_provider import (
    DingTalkProviderConfig,
    FeishuProviderConfig,
    WeComProviderConfig,
    WPS365ProviderConfig,
    fetch_sso_providers,
)
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.utils.logger import setup_logger
from onyx.utils.url import sanitize_next_url
from shared_configs.contextvars import (
    CURRENT_TENANT_ID_CONTEXTVAR,
    SESSION_TENANT_OVERRIDE_CONTEXTVAR,
    get_current_tenant_id,
)

logger = setup_logger()

router = APIRouter(prefix="/auth/china")

_NO_WORKSPACE_DETAIL = (
    "Sign-in did not identify a workspace. Return to the login page and enter "
    "your email to continue."
)
_STATE_TENANT_KEY = "tenant_id"
_COOKIE_SECURE = WEB_DOMAIN.startswith("https")

_CHINA_PROVIDER_TYPES = {
    SSOProviderType.WECOM,
    SSOProviderType.DINGTALK,
    SSOProviderType.FEISHU,
    SSOProviderType.WPS365,
}


@dataclass(frozen=True)
class ChinaIdentity:
    """Normalized identity returned by a platform exchange."""

    account_id: str
    email: str
    display_name: str
    access_token: str
    departments: tuple[str, ...] = ()


class ChinaSsoError(Exception):
    """A platform exchange failed; message is safe to log and show."""


# ── provider row resolution ───────────────────────────────────────────────


def resolve_china_provider(
    db_session: Session, provider_name: str
) -> tuple[SSOProvider, Any]:
    for provider in fetch_sso_providers(db_session):
        if provider.name == provider_name:
            if provider.provider_type not in _CHINA_PROVIDER_TYPES:
                raise OnyxError(
                    OnyxErrorCode.VALIDATION_ERROR,
                    f"Provider {provider_name!r} is not a China platform provider",
                )
            stored_config = (
                provider.config.get_value(apply_mask=False) if provider.config else {}
            )
            return provider, _config_for(provider, dict(stored_config))
    raise OnyxError(
        OnyxErrorCode.VALIDATION_ERROR,
        f"Unknown SSO provider {provider_name!r}",
    )


def _config_for(provider: SSOProvider, config: dict[str, Any]) -> Any:
    model = {
        SSOProviderType.WECOM: WeComProviderConfig,
        SSOProviderType.DINGTALK: DingTalkProviderConfig,
        SSOProviderType.FEISHU: FeishuProviderConfig,
        SSOProviderType.WPS365: WPS365ProviderConfig,
    }[provider.provider_type]
    return model.model_validate(config)


# ── authorize URL builders (pure, unit-tested) ────────────────────────────


def wecom_authorize_url(
    config: WeComProviderConfig, state: str, redirect_uri: str
) -> str:
    return (
        "https://login.work.weixin.qq.com/wwlogin/sso/login"
        "?login_type=CorpApp"
        f"&appid={quote_plus(config.corp_id)}"
        f"&agentid={quote_plus(config.agent_id)}"
        f"&redirect_uri={quote_plus(redirect_uri, safe='')}"
        f"&state={quote_plus(state)}"
    )


def dingtalk_authorize_url(
    config: DingTalkProviderConfig, state: str, redirect_uri: str
) -> str:
    return (
        "https://login.dingtalk.com/oauth2/auth"
        f"?redirect_uri={quote_plus(redirect_uri, safe='')}"
        "&response_type=code"
        f"&client_id={quote_plus(config.client_id)}"
        "&scope=openid"
        f"&state={quote_plus(state)}"
        "&prompt=consent"
    )


# Passport only fills `email` on /oauth/userinfo when the grant covers the
# contact read scopes; logins without them fall back to the deterministic
# `{union_id}@{email_domain}` identity.
FEISHU_LOGIN_SCOPES = "contact:user.base:readonly contact:user.email:readonly"


def feishu_authorize_url(
    config: FeishuProviderConfig, state: str, redirect_uri: str
) -> str:
    return (
        "https://passport.feishu.cn/suite/passport/oauth/authorize"
        f"?client_id={quote_plus(config.app_id)}"
        f"&redirect_uri={quote_plus(redirect_uri, safe='')}"
        "&response_type=code"
        f"&scope={quote_plus(FEISHU_LOGIN_SCOPES)}"
        f"&state={quote_plus(state)}"
    )


def wps365_authorize_url(
    config: WPS365ProviderConfig, state: str, redirect_uri: str
) -> str:
    base = config.base_url.rstrip("/")
    return (
        f"{base}/oauth2/v3/authorize"
        f"?client_id={quote_plus(config.client_id)}"
        f"&redirect_uri={quote_plus(redirect_uri, safe='')}"
        "&response_type=code"
        f"&state={quote_plus(state)}"
    )


_AUTHORIZE_URL_BUILDERS = {
    SSOProviderType.WECOM: wecom_authorize_url,
    SSOProviderType.DINGTALK: dingtalk_authorize_url,
    SSOProviderType.FEISHU: feishu_authorize_url,
    SSOProviderType.WPS365: wps365_authorize_url,
}


# ── code exchanges (httpx.AsyncClient injected for tests) ─────────────────


def _email_for(account_key: str, email: str | None, email_domain: str) -> str:
    if email and "@" in email:
        return email
    return f"{account_key}@{email_domain}"


async def _wecom_corp_access_token(
    client: httpx.AsyncClient, config: WeComProviderConfig
) -> str:
    resp = await client.get(
        "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
        params={"corpid": config.corp_id, "corpsecret": config.corp_secret},
    )
    data = resp.json()
    if data.get("errcode") not in (0, None):
        raise ChinaSsoError(f"WeCom token error: {data.get('errmsg')}")
    token = data.get("access_token")
    if not token:
        raise ChinaSsoError("WeCom returned no access token")
    return str(token)


async def wecom_exchange(
    client: httpx.AsyncClient, config: WeComProviderConfig, code: str
) -> ChinaIdentity:
    corp_token = await _wecom_corp_access_token(client, config)
    resp = await client.get(
        "https://qyapi.weixin.qq.com/cgi-bin/auth/getuserinfo",
        params={"access_token": corp_token, "code": code},
    )
    data = resp.json()
    if data.get("errcode") not in (0, None):
        raise ChinaSsoError(f"WeCom userinfo error: {data.get('errmsg')}")
    userid = data.get("userid")
    if not userid:
        raise ChinaSsoError("WeCom returned no userid (external contact?)")
    detail_resp = await client.get(
        "https://qyapi.weixin.qq.com/cgi-bin/user/get",
        params={"access_token": corp_token, "userid": userid},
    )
    detail = detail_resp.json()
    if detail.get("errcode") not in (0, None):
        detail = {}
    departments: tuple[str, ...] = ()
    dept_ids = detail.get("department") or []
    if dept_ids:
        dept_list = (
            await client.get(
                "https://qyapi.weixin.qq.com/cgi-bin/department/list",
                params={"access_token": corp_token},
            )
        ).json()
        name_by_id = {
            item.get("id"): item.get("name")
            for item in dept_list.get("department") or []
        }
        departments = tuple(str(name_by_id[d]) for d in dept_ids if name_by_id.get(d))
    email = detail.get("biz_mail") or detail.get("email")
    return ChinaIdentity(
        account_id=f"wecom:{config.corp_id}:{userid}",
        email=_email_for(userid, email, config.email_domain),
        display_name=str(detail.get("name") or userid),
        access_token=corp_token,
        departments=departments,
    )


async def dingtalk_exchange(
    client: httpx.AsyncClient, config: DingTalkProviderConfig, code: str
) -> ChinaIdentity:
    resp = await client.post(
        "https://api.dingtalk.com/v1.0/oauth2/userAccessToken",
        json={
            "clientId": config.client_id,
            "clientSecret": config.client_secret,
            "code": code,
            "grantType": "authorization_code",
        },
    )
    data = resp.json()
    token = data.get("accessToken")
    if not token:
        raise ChinaSsoError(f"DingTalk token error: {data.get('message') or data}")
    me_resp = await client.get(
        "https://api.dingtalk.com/v1.0/contact/users/me",
        headers={"x-acs-dingtalk-access-token": token},
    )
    me = me_resp.json()
    union_id = me.get("unionId")
    if not union_id:
        raise ChinaSsoError("DingTalk returned no unionId")
    departments = await _dingtalk_departments(client, config, union_id)
    return ChinaIdentity(
        account_id=f"dingtalk:{config.client_id}:{union_id}",
        email=_email_for(union_id, me.get("email"), config.email_domain),
        display_name=str(me.get("nick") or union_id),
        access_token=str(token),
        departments=departments,
    )


async def _dingtalk_departments(
    client: httpx.AsyncClient, config: DingTalkProviderConfig, union_id: str
) -> tuple[str, ...]:
    """Best-effort department names for the login user (never raises).

    unionid → userid (corp token) → user detail with dept_id_list →
    department names via a bounded listsub walk."""
    try:
        token_resp = await client.post(
            "https://api.dingtalk.com/v1.0/oauth2/accessToken",
            json={"appKey": config.client_id, "appSecret": config.client_secret},
        )
        corp_token = token_resp.json().get("accessToken")
        if not corp_token:
            return ()
        union_resp = await client.post(
            "https://oapi.dingtalk.com/topapi/user/getByUnionid",
            params={"access_token": corp_token},
            json={"unionid": union_id},
        )
        userid = (union_resp.json().get("result") or {}).get("userid")
        if not userid:
            return ()
        user_resp = await client.post(
            "https://oapi.dingtalk.com/topapi/v2/user/get",
            params={"access_token": corp_token},
            json={"userid": userid},
        )
        dept_ids = (user_resp.json().get("result") or {}).get("dept_id_list") or []
        if not dept_ids:
            return ()
        name_by_id = await _dingtalk_department_names(client, corp_token)
        return tuple(name for d in dept_ids if (name := name_by_id.get(d)) is not None)
    except Exception:
        logger.warning("DingTalk department sync failed", exc_info=True)
        return ()


async def _dingtalk_department_names(
    client: httpx.AsyncClient, corp_token: str
) -> dict[int, str]:
    """dept_id → name for the org tree, via bounded listsub recursion."""
    name_by_id: dict[int, str] = {}
    frontier = [1]  # DingTalk root department id
    for _depth in range(5):
        next_frontier: list[int] = []
        for dept_id in frontier:
            resp = await client.post(
                "https://oapi.dingtalk.com/topapi/v2/department/listsub",
                params={"access_token": corp_token},
                json={"dept_id": dept_id},
            )
            for item in resp.json().get("result") or []:
                child_id = item.get("dept_id")
                if child_id is None:
                    continue
                name_by_id[int(child_id)] = str(item.get("name") or child_id)
                next_frontier.append(int(child_id))
            if len(name_by_id) >= 500:  # bound the walk for large orgs
                return name_by_id
        if not next_frontier:
            break
        frontier = next_frontier
    return name_by_id


async def feishu_exchange(
    client: httpx.AsyncClient, config: FeishuProviderConfig, code: str
) -> ChinaIdentity:
    resp = await client.post(
        "https://passport.feishu.cn/suite/passport/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": config.app_id,
            "client_secret": config.app_secret,
            "code": code,
        },
    )
    data = resp.json()
    token = data.get("access_token")
    if not token:
        raise ChinaSsoError(
            f"Feishu token error: {data.get('error_description') or data}"
        )
    info_resp = await client.get(
        "https://passport.feishu.cn/suite/passport/oauth/userinfo",
        headers={"Authorization": f"Bearer {token}"},
    )
    info = info_resp.json()
    union_id = info.get("union_id") or info.get("open_id")
    if not union_id:
        raise ChinaSsoError("Feishu returned no union_id/open_id")
    departments = await _feishu_departments(client, config, union_id)
    return ChinaIdentity(
        account_id=f"feishu:{config.app_id}:{union_id}",
        email=_email_for(union_id, info.get("email"), config.email_domain),
        display_name=str(info.get("name") or union_id),
        access_token=str(token),
        departments=departments,
    )


async def _feishu_departments(
    client: httpx.AsyncClient, config: FeishuProviderConfig, open_id: str
) -> tuple[str, ...]:
    """Best-effort department names via the app's tenant token
    (requires the contact read scope); never raises."""
    try:
        token_resp = await client.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": config.app_id, "app_secret": config.app_secret},
        )
        data = token_resp.json()
        tenant_token = data.get("tenant_access_token")
        if not tenant_token:
            return ()
        headers = {"Authorization": f"Bearer {tenant_token}"}
        users_resp = await client.get(
            "https://open.feishu.cn/open-apis/contact/v3/users/batch_get",
            params={"user_id_type": "open_id", "user_ids": open_id},
            headers=headers,
        )
        users = (users_resp.json().get("data") or {}).get("users") or []
        dept_ids = list((users[0] if users else {}).get("department_ids") or [])
        names: list[str] = []
        for dept_id in dept_ids[:10]:  # bound: humans sit in few departments
            dept_resp = await client.get(
                f"https://open.feishu.cn/open-apis/contact/v3/departments/{dept_id}",
                params={"department_id_type": "open_department_id"},
                headers=headers,
            )
            dept = (dept_resp.json().get("data") or {}).get("department") or {}
            if dept.get("name"):
                names.append(str(dept["name"]))
        return tuple(names)
    except Exception:
        logger.warning("Feishu department sync failed", exc_info=True)
        return ()


async def wps365_exchange(
    client: httpx.AsyncClient, config: WPS365ProviderConfig, code: str
) -> ChinaIdentity:
    base = config.base_url.rstrip("/")
    resp = await client.post(
        f"{base}/oauth2/v3/token",
        data={
            "grant_type": "authorization_code",
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "code": code,
        },
    )
    data = resp.json()
    token = data.get("access_token")
    if not token:
        raise ChinaSsoError(
            f"WPS365 token error: {data.get('error_description') or data}"
        )
    info_resp = await client.get(
        f"{base}/oauth2/v3/userinfo",
        headers={"Authorization": f"Bearer {token}"},
    )
    info = info_resp.json()
    sub = info.get("sub") or info.get("user_id") or info.get("id")
    if not sub:
        raise ChinaSsoError("WPS365 returned no subject")
    return ChinaIdentity(
        account_id=f"wps365:{config.client_id}:{sub}",
        email=_email_for(sub, info.get("email"), config.email_domain),
        display_name=str(info.get("name") or sub),
        access_token=str(token),
    )


_EXCHANGERS = {
    SSOProviderType.WECOM: wecom_exchange,
    SSOProviderType.DINGTALK: dingtalk_exchange,
    SSOProviderType.FEISHU: feishu_exchange,
    SSOProviderType.WPS365: wps365_exchange,
}


# ── adapter satisfying complete_login_flow's oauth_client interface ───────


class ChinaOAuthClient(BaseOAuth2[Any]):
    """``complete_login_flow`` client adapter.

    The identity is already resolved by the platform exchange, so
    ``get_id_email`` returns it without a provider round-trip.
    """

    def __init__(self, oauth_name: str, identity: ChinaIdentity) -> None:
        self.name = oauth_name
        self._identity = identity

    async def get_id_email(self, token: str) -> tuple[str, str]:
        del token
        return self._identity.account_id, self._identity.email


# ── workspace session handling (mirrors oidc_multi) ───────────────────────


@contextmanager
def _workspace_session(tenant_id: str | None) -> Generator[Session, None, None]:
    if not MULTI_TENANT:
        with get_session_with_current_tenant() as db_session:
            yield db_session
        return
    if not tenant_id:
        raise OnyxError(OnyxErrorCode.UNAUTHORIZED, _NO_WORKSPACE_DETAIL)
    context_token = CURRENT_TENANT_ID_CONTEXTVAR.set(tenant_id)
    try:
        with get_session_with_tenant(tenant_id=tenant_id) as db_session:
            yield db_session
    finally:
        CURRENT_TENANT_ID_CONTEXTVAR.reset(context_token)


@contextmanager
def _pinned_workspace(tenant_id: str | None) -> Generator[None, None, None]:
    if not MULTI_TENANT:
        yield
        return
    if not tenant_id:
        raise OnyxError(OnyxErrorCode.UNAUTHORIZED, _NO_WORKSPACE_DETAIL)
    tenant_token = CURRENT_TENANT_ID_CONTEXTVAR.set(tenant_id)
    override_token = SESSION_TENANT_OVERRIDE_CONTEXTVAR.set(tenant_id)
    try:
        yield
    finally:
        SESSION_TENANT_OVERRIDE_CONTEXTVAR.reset(override_token)
        CURRENT_TENANT_ID_CONTEXTVAR.reset(tenant_token)


def _state_tenant(state_data: dict[str, Any]) -> str | None:
    tenant_id = state_data.get(_STATE_TENANT_KEY)
    return tenant_id if isinstance(tenant_id, str) and tenant_id else None


# ── routes ────────────────────────────────────────────────────────────────


def _callback_uri() -> str:
    # The platform redirects the browser, so route through /api to reach
    # FastAPI behind the same proxy the OIDC flow uses.
    return f"{WEB_DOMAIN}/api/auth/china/callback"


@router.get("/{provider_name}/authorize")
async def china_sso_authorize(
    provider_name: str,
    request: Request,
) -> Response:
    workspace_token = request.query_params.get(SSO_TENANT_TOKEN_PARAM)
    tenant_id = decode_sso_tenant_token(workspace_token) if workspace_token else None
    with _workspace_session(tenant_id) as db_session:
        provider, config = resolve_china_provider(db_session, provider_name)
    next_url = sanitize_next_url(request.query_params.get("next"))
    csrf_token = generate_csrf_token()
    state = generate_state_token(
        {
            "next_url": next_url,
            "provider_name": provider_name,
            _STATE_TENANT_KEY: get_current_tenant_id(),
            CSRF_TOKEN_KEY: csrf_token,
        },
        USER_AUTH_SECRET,
    )
    builder = _AUTHORIZE_URL_BUILDERS[provider.provider_type]
    authorization_url = builder(config, state, _callback_uri())  # type: ignore[arg-type]
    response = JSONResponse(content={"authorization_url": authorization_url})
    response.set_cookie(
        CSRF_TOKEN_COOKIE_NAME,
        csrf_token,
        httponly=True,
        # "lax" (matching the OIDC flow): the OAuth callback is a top-level
        # GET redirect, so the CSRF cookie survives it. "none" without a
        # secure context gets dropped by the browser on http:// deployments,
        # which broke the double-submit check at the callback.
        samesite="lax",
        secure=_COOKIE_SECURE,
    )
    return response


@router.get("/callback")
async def china_sso_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    user_manager: UserManager = Depends(get_user_manager),
) -> Response:
    if error is not None:
        raise OnyxError(OnyxErrorCode.VALIDATION_ERROR, f"SSO provider error: {error}")
    if state is None or code is None:
        raise OnyxError(OnyxErrorCode.VALIDATION_ERROR, "Missing code or state")

    state_data = decode_and_validate_oauth_state(
        request=request,
        state_value=state,
        state_secret=USER_AUTH_SECRET,
    )
    provider_name = str(state_data.get("provider_name") or "")
    if not provider_name:
        raise OnyxError(OnyxErrorCode.VALIDATION_ERROR, "State carries no provider")

    tenant_id = _state_tenant(state_data)
    with _workspace_session(tenant_id) as db_session:
        provider, config = resolve_china_provider(db_session, provider_name)

        async with httpx.AsyncClient(timeout=15) as client:
            exchanger = _EXCHANGERS[provider.provider_type]
            identity = await exchanger(client, config, code)  # type: ignore[arg-type]

        oauth_client = ChinaOAuthClient(provider.provider_type.value.lower(), identity)
        strategy = auth_backend.get_strategy()
        with _pinned_workspace(tenant_id):
            redirect_response = await complete_login_flow(
                oauth_client=oauth_client,
                token=OAuth2Token({"access_token": identity.access_token}),
                state_data=state_data,
                request=request,
                user_manager=user_manager,
                backend=auth_backend,
                strategy=strategy,  # ty: ignore[invalid-argument-type]
                associate_by_email=True,
                is_verified_by_default=True,
            )
            if identity.departments:
                _sync_departments_best_effort(
                    db_session, identity.email, identity.departments
                )
    return redirect_response


def _sync_departments_best_effort(
    db_session: Session, user_email: str, departments: tuple[str, ...]
) -> None:
    """Map platform departments onto Onyx user groups; never raises."""
    try:
        from onyx.db.user_group_ce import assign_user_to_groups_by_name

        assign_user_to_groups_by_name(
            db_session, user_email=user_email, group_names=list(departments)
        )
        db_session.commit()
    except Exception:
        db_session.rollback()
        logger.exception("Department-to-group sync failed for %s", user_email)
