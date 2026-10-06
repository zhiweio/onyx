from onyx.db.enums import ExternalAppType
from onyx.external_apps.providers.base import OAuthExternalAppProvider
from onyx.external_apps.providers.dingtalk import DingTalkAction, DingTalkProvider
from onyx.external_apps.providers.feishu import FeishuAction, FeishuProvider
from onyx.external_apps.providers.registry import (
    PROVIDERS,
    fetch_available_built_in_apps,
    get_endpoint_catalog,
)
from onyx.external_apps.providers.wecom import WeComProvider
from onyx.external_apps.providers.wps365 import WPS365Provider


def test_china_providers_are_registered() -> None:
    assert PROVIDERS[ExternalAppType.FEISHU] is not None
    assert PROVIDERS[ExternalAppType.DINGTALK] is not None
    assert PROVIDERS[ExternalAppType.WECOM] is not None
    assert PROVIDERS[ExternalAppType.WPS365] is not None


def test_china_providers_surface_in_built_in_options() -> None:
    descriptors = fetch_available_built_in_apps()
    names = {d.app_type for d in descriptors}
    assert {
        ExternalAppType.FEISHU,
        ExternalAppType.DINGTALK,
        ExternalAppType.WECOM,
        ExternalAppType.WPS365,
    } <= names


def test_feishu_catalog_covers_core_actions() -> None:
    catalog = get_endpoint_catalog(ExternalAppType.FEISHU)
    ids = {endpoint.id for endpoint in catalog}
    assert {
        FeishuAction.MESSAGE_SEND,
        FeishuAction.DOCS_SEARCH,
        FeishuAction.DOC_READ,
    } <= ids
    # Message sending governs tighter than reads by default.
    send = next(e for e in catalog if e.id == FeishuAction.MESSAGE_SEND)
    assert send.default_policy.value == "ASK"


def test_feishu_oauth_uses_app_id_credential_keys() -> None:
    """Feishu's console calls the OAuth client credentials app_id/app_secret;
    the start/refresh paths must look those keys up, not client_id/secret."""
    provider = FeishuProvider()
    assert isinstance(provider, OAuthExternalAppProvider)
    assert provider.spec.client_credential_keys == ("app_id", "app_secret")
    org_fields = {
        f.key for f in provider.spec.descriptor.required_org_credential_fields
    }
    assert org_fields == set(provider.spec.client_credential_keys)


def test_dingtalk_is_org_credential_with_derived_token() -> None:
    """DingTalk's new-gen OpenAPI authenticates corp-wide: org credentials are
    the app's client_id/client_secret, the access token is derived at egress
    time (org_token spec), and the catalog governs api.dingtalk.com only —
    the legacy oapi host takes the token as a query param the header template
    can't inject."""
    provider = DingTalkProvider()
    assert not isinstance(provider, OAuthExternalAppProvider)
    assert provider.spec.descriptor.upstream_url_patterns == [
        "https://api\\.dingtalk\\.com/.*"
    ]
    assert provider.spec.descriptor.auth_template == {
        "x-acs-dingtalk-access-token": "{access_token}"
    }
    keys = {f.key for f in provider.spec.descriptor.required_org_credential_fields}
    assert keys == {"client_id", "client_secret"}
    assert provider.spec.org_token is not None
    assert provider.spec.org_token.kind == "dingtalk_corp"
    assert provider.spec.org_token.credential_keys == ("client_id", "client_secret")
    # DingTalk renames the token response fields.
    assert provider.spec.org_token.response_token_key == "accessToken"
    assert provider.spec.org_token.response_expires_key == "expireIn"


def test_dingtalk_catalog_covers_core_actions() -> None:
    catalog = get_endpoint_catalog(ExternalAppType.DINGTALK)
    ids = {endpoint.id for endpoint in catalog}
    assert {
        DingTalkAction.KB_LIST,
        DingTalkAction.DRIVE_FILES_LIST,
        DingTalkAction.TODO_TASKS_LIST,
        DingTalkAction.CALENDAR_EVENTS_LIST,
        DingTalkAction.CONTACT_USERS_SEARCH,
    } <= ids
    # The token endpoints and deletes are denied by default; sends need approval.
    by_id = {endpoint.id: endpoint for endpoint in catalog}
    assert by_id[DingTalkAction.AUTH_CORP_TOKEN].default_policy.value == "DENY"
    assert by_id[DingTalkAction.TODO_TASK_DELETE].default_policy.value == "DENY"
    assert by_id[DingTalkAction.ROBOT_O2O_SEND].default_policy.value == "ASK"
    assert by_id[DingTalkAction.KB_NODE_CONTENT_GET].default_policy.value == "ALWAYS"


def test_wecom_is_org_credential_only_with_derived_token() -> None:
    """WeCom's CLI gateway has no per-user OAuth: org credentials are the
    smart robot's bot_id/bot_secret, the bearer token is derived at egress
    time (org_token spec), and the catalog governs the gateway surface."""
    provider = WeComProvider()
    assert not isinstance(provider, OAuthExternalAppProvider)
    assert provider.spec.endpoint_catalog
    assert provider.spec.descriptor.auth_template == {
        "Authorization": "Bearer {access_token}"
    }
    keys = {f.key for f in provider.spec.descriptor.required_org_credential_fields}
    assert keys == {"bot_id", "bot_secret"}
    assert provider.spec.org_token is not None
    assert provider.spec.org_token.kind == "wecom_cli"
    assert provider.spec.org_token.credential_keys == ("bot_id", "bot_secret")


def test_wps365_reuses_sso_account_endpoints() -> None:
    provider = WPS365Provider()
    assert isinstance(provider, OAuthExternalAppProvider)
    assert provider.spec.oauth.authorize_url.startswith(
        "https://account.wps.cn/oauth2/v3/"
    )
    assert provider.spec.oauth.token_url == "https://account.wps.cn/oauth2/v3/token"
