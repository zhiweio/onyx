from typing import Any

from onyx.db.enums import ExternalAppType
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.external_apps.providers.base import (
    AdminDescriptorSpec,
    OAuthExternalAppProvider,
    OAuthFlowSpec,
    OAuthProviderSpec,
    OrgCredentialField,
)

# Regional endpoints; the cn (default) region matches the SSO integration.
_WPS365_ACCOUNT_BASE = "https://account.wps.cn"


class WPS365Provider(OAuthExternalAppProvider):
    """WPS 365 as a user-OAuth app.

    Reuses the account-service OAuth endpoints the SSO integration uses. The
    action catalog starts empty and fills in as the WPS 365 open APIs are
    verified per deployment — catalog additions propagate without migration.
    """

    spec = OAuthProviderSpec(
        app_type=ExternalAppType.WPS365,
        app_name="WPS 365",
        oauth=OAuthFlowSpec(
            authorize_url=f"{_WPS365_ACCOUNT_BASE}/oauth2/v3/authorize",
            token_url=f"{_WPS365_ACCOUNT_BASE}/oauth2/v3/token",
            scope="openid",
            scope_param="scope",
        ),
        descriptor=AdminDescriptorSpec(
            upstream_url_patterns=[
                "https://www\\.wps\\.cn/.*",
                "https://open\\.wps\\.cn/.*",
                "https://www\\.kdocs\\.cn/.*",
            ],
            auth_template={"Authorization": "Bearer {access_token}"},
            required_org_credential_fields=[
                OrgCredentialField(
                    key="client_id",
                    label="Client ID",
                    description=("The OAuth client ID from the WPS 365 open platform."),
                ),
                OrgCredentialField(
                    key="client_secret",
                    label="Client Secret",
                    description=(
                        "The OAuth client secret. Treat this like a password."
                    ),
                    secret=True,
                ),
            ],
            setup_instructions=(
                "On the WPS 365 open platform: create an OAuth application, "
                "add this Onyx instance's callback URL "
                "(/craft/v1/apps/oauth/callback) to the allowed redirect "
                "URLs, then paste the Client ID and Client Secret below. "
                "Agent actions for WPS 365 arrive with a later update."
            ),
        ),
        endpoint_catalog=[],
    )

    def extract_credentials(self, response_data: dict[str, Any]) -> dict[str, Any]:
        access_token = response_data.get("access_token")
        if not access_token:
            raise OnyxError(
                OnyxErrorCode.BAD_GATEWAY,
                "WPS 365 OAuth response did not contain an access token.",
            )
        creds: dict[str, Any] = {
            "access_token": access_token,
            "token_type": response_data.get("token_type"),
        }
        if response_data.get("refresh_token"):
            creds["refresh_token"] = response_data["refresh_token"]
        if response_data.get("expires_in"):
            creds["expires_in"] = response_data["expires_in"]
        return creds
