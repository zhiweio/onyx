from typing import Any

import requests

from onyx.db.enums import EndpointPolicy, ExternalAppType
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.external_apps.providers.actions import (
    EndpointSpec,
    ExternalAppAction,
    RestRoute,
)
from onyx.external_apps.providers.base import (
    AdminDescriptorSpec,
    OAuthExternalAppProvider,
    OAuthFlowSpec,
    OAuthProviderSpec,
    OrgCredentialField,
    TokenExchangeRequest,
    TokenRefreshTerminalError,
    TokenRefreshTransientError,
    token_response_error,
)


class DingTalkAction(ExternalAppAction):
    """Strongly-typed catalog ids for the DingTalk provider."""

    PROFILE_READ = "dingtalk.profile.read"


_ENDPOINTS: list[EndpointSpec] = [
    EndpointSpec(
        id=DingTalkAction.PROFILE_READ,
        normalised_name="Read the connected user",
        description="Read the authenticated user's DingTalk profile.",
        matches=(RestRoute(method="GET", path="/v1.0/contact/users/me"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
]


class DingTalkProvider(OAuthExternalAppProvider):
    """DingTalk user-token OAuth.

    DingTalk's token endpoint speaks JSON with renamed fields
    (``clientId``/``clientSecret``/``grantType``), so both the initial
    exchange and the refresh are overridden off the RFC-6749 form defaults.
    """

    spec = OAuthProviderSpec(
        app_type=ExternalAppType.DINGTALK,
        app_name="DingTalk",
        oauth=OAuthFlowSpec(
            authorize_url="https://login.dingtalk.com/oauth2/auth",
            token_url="https://api.dingtalk.com/v1.0/oauth2/userAccessToken",
            scope="openid",
            scope_param="scope",
            extra_authorize_params={"response_type": "code", "prompt": "consent"},
        ),
        descriptor=AdminDescriptorSpec(
            upstream_url_patterns=["https://api\\.dingtalk\\.com/.*"],
            auth_template={"x-acs-dingtalk-access-token": "{access_token}"},
            required_org_credential_fields=[
                OrgCredentialField(
                    key="client_id",
                    label="Client ID (AppKey)",
                    description=(
                        "The app's AppKey from the DingTalk developer console."
                    ),
                ),
                OrgCredentialField(
                    key="client_secret",
                    label="Client Secret (AppSecret)",
                    description="The app's AppSecret. Treat this like a password.",
                    secret=True,
                ),
            ],
            setup_instructions=(
                "In the DingTalk developer console: create an enterprise "
                "internal app, add this Onyx instance's callback URL "
                "(/craft/v1/apps/oauth/callback) to the login redirect URLs, "
                "and request the personal information and address book "
                "permissions. Then paste the AppKey and AppSecret below."
            ),
        ),
        endpoint_catalog=_ENDPOINTS,
    )

    def extract_credentials(self, response_data: dict[str, Any]) -> dict[str, Any]:
        access_token = response_data.get("accessToken") or response_data.get(
            "access_token"
        )
        if not access_token:
            raise OnyxError(
                OnyxErrorCode.BAD_GATEWAY,
                "DingTalk OAuth response did not contain an access token.",
            )
        creds: dict[str, Any] = {"access_token": access_token}
        if response_data.get("refreshToken"):
            creds["refresh_token"] = response_data["refreshToken"]
        if response_data.get("expireIn"):
            creds["expires_in"] = response_data["expireIn"]
        return creds

    def build_token_exchange_request(
        self,
        code: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,  # noqa: ARG002 - signature mirrors the base hook
    ) -> TokenExchangeRequest:
        return TokenExchangeRequest(
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            body={
                "clientId": client_id,
                "clientSecret": client_secret,
                "code": code,
                "grantType": "authorization_code",
            },
            json_encoded=True,
        )

    def refresh_credentials(
        self,
        stored: dict[str, Any],
        client_id: str,
        client_secret: str,
    ) -> dict[str, Any]:
        refresh_token = stored.get("refresh_token")
        if not refresh_token:
            raise TokenRefreshTerminalError(
                "No refresh token stored; the user must reconnect."
            )
        try:
            response = requests.post(
                self.spec.oauth.token_url,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json={
                    "clientId": client_id,
                    "clientSecret": client_secret,
                    "refreshToken": refresh_token,
                    "grantType": "refresh_token",
                },
                timeout=self.refresh_http_timeout_seconds,
            )
        except requests.RequestException as exc:
            raise TokenRefreshTransientError(f"network error: {exc}") from exc
        try:
            body = response.json()
        except ValueError as exc:
            raise TokenRefreshTransientError(
                f"non-JSON token response (status={response.status_code})"
            ) from exc

        error = token_response_error(response, body)
        if error is not None:
            if error in self.terminal_refresh_errors:
                raise TokenRefreshTerminalError(error)
            raise TokenRefreshTransientError(error)

        mapped = self.extract_credentials(body)
        return {**stored, **mapped}
