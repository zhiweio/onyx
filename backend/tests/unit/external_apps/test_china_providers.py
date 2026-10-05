from onyx.db.enums import ExternalAppType
from onyx.external_apps.providers.base import OAuthExternalAppProvider
from onyx.external_apps.providers.dingtalk import DingTalkProvider
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


def test_dingtalk_is_oauth_with_json_exchange() -> None:
    provider = DingTalkProvider()
    assert isinstance(provider, OAuthExternalAppProvider)
    request = provider.build_token_exchange_request(
        "code-1", "client-id", "client-secret", "https://example.com/cb"
    )
    assert request.json_encoded is True
    assert request.body["clientId"] == "client-id"
    assert request.body["grantType"] == "authorization_code"


def test_wecom_is_org_credential_only() -> None:
    provider = WeComProvider()
    assert not isinstance(provider, OAuthExternalAppProvider)
    assert provider.spec.endpoint_catalog == []
    assert provider.spec.descriptor.auth_template == {}
    keys = {f.key for f in provider.spec.descriptor.required_org_credential_fields}
    assert keys == {"corp_id", "corp_secret", "agent_id"}


def test_wps365_reuses_sso_account_endpoints() -> None:
    provider = WPS365Provider()
    assert isinstance(provider, OAuthExternalAppProvider)
    assert provider.spec.oauth.authorize_url.startswith(
        "https://account.wps.cn/oauth2/v3/"
    )
    assert provider.spec.oauth.token_url == "https://account.wps.cn/oauth2/v3/token"
