from typing import Any

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
)


class FeishuAction(ExternalAppAction):
    """Strongly-typed catalog ids for the Feishu provider."""

    MESSAGE_SEND = "feishu.message.send"
    DOCS_SEARCH = "feishu.docs.search"
    DOC_READ = "feishu.doc.read"


# open.feishu.cn REST surface; every action rides with the user_access_token
# obtained through passport.feishu.cn (see OAuthFlowSpec).
_ENDPOINTS: list[EndpointSpec] = [
    EndpointSpec(
        id=FeishuAction.MESSAGE_SEND,
        normalised_name="Send a message",
        description="Send a message to a chat the user belongs to.",
        matches=(RestRoute(method="POST", path="/open-apis/im/v1/messages"),),
    ),
    EndpointSpec(
        id=FeishuAction.DOCS_SEARCH,
        normalised_name="Search documents",
        description="Search the workspace's cloud documents.",
        matches=(
            RestRoute(method="POST", path="/open-apis/suite/docs-api/search/object"),
        ),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=FeishuAction.DOC_READ,
        normalised_name="Read a document",
        description="Read a docx document's text content.",
        matches=(
            RestRoute(
                method="GET",
                path="/open-apis/docx/v1/documents/{document_id}/raw_content",
            ),
        ),
        default_policy=EndpointPolicy.ALWAYS,
    ),
]


class FeishuProvider(OAuthExternalAppProvider):
    spec = OAuthProviderSpec(
        app_type=ExternalAppType.FEISHU,
        app_name="Feishu",
        oauth=OAuthFlowSpec(
            authorize_url=("https://passport.feishu.cn/suite/passport/oauth/authorize"),
            token_url="https://passport.feishu.cn/suite/passport/oauth/token",
            scope="openid offline_access",
            scope_param="scope",
        ),
        descriptor=AdminDescriptorSpec(
            upstream_url_patterns=["https://open\\.feishu\\.cn/.*"],
            auth_template={"Authorization": "Bearer {access_token}"},
            required_org_credential_fields=[
                OrgCredentialField(
                    key="app_id",
                    label="App ID",
                    description="Feishu app ID (App ID), from the developer console.",
                ),
                OrgCredentialField(
                    key="app_secret",
                    label="App Secret",
                    description="The Feishu app secret. Treat this like a password.",
                    secret=True,
                ),
            ],
            setup_instructions=(
                "In the Feishu developer console: create an enterprise "
                "self-built app, enable the web application, add this Onyx "
                "instance's callback URL (/craft/v1/apps/oauth/callback) to "
                "the redirect URLs, and grant the im:message:send, "
                "docs:doc:readonly and search permissions. Then paste the App "
                "ID and App Secret below."
            ),
        ),
        endpoint_catalog=_ENDPOINTS,
    )

    def extract_credentials(self, response_data: dict[str, Any]) -> dict[str, Any]:
        access_token = response_data.get("access_token")
        if not access_token:
            raise OnyxError(
                OnyxErrorCode.BAD_GATEWAY,
                "Feishu OAuth response did not contain an access token.",
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
