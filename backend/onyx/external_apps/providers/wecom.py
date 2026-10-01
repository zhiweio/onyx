from onyx.db.enums import ExternalAppType
from onyx.external_apps.providers.base import (
    AdminDescriptorSpec,
    ExternalAppProvider,
    OrgCredentialField,
    ProviderSpec,
)


class WeComProvider(ExternalAppProvider):
    """WeCom (企业微信) as an org-credential app.

    WeCom has no per-user OAuth for server-side calls: every API rides on the
    app-level access token fetched with the corp secret, and that token
    travels as a query parameter rather than a header, so the catalog stays
    empty until the egress layer can express query-param auth. Configuring
    the org credentials now registers the app and its egress domains.
    """

    spec = ProviderSpec(
        app_type=ExternalAppType.WECOM,
        app_name="WeCom",
        descriptor=AdminDescriptorSpec(
            upstream_url_patterns=["https://qyapi\\.weixin\\.qq\\.com/.*"],
            auth_template={},
            required_org_credential_fields=[
                OrgCredentialField(
                    key="corp_id",
                    label="Corp ID",
                    description="WeCom enterprise ID (企业ID), from the admin console.",
                ),
                OrgCredentialField(
                    key="corp_secret",
                    label="Corp Secret",
                    description=(
                        "The self-built app's secret. Treat this like a password."
                    ),
                    secret=True,
                ),
                OrgCredentialField(
                    key="agent_id",
                    label="Agent ID",
                    description="The self-built app's agent ID (应用AgentId).",
                ),
            ],
            setup_instructions=(
                "In the WeCom admin console: open the self-built app used by "
                "this Onyx deployment, note its Corp ID (企业ID), Agent ID, and "
                "Secret, and paste them below. Agent actions for WeCom arrive "
                "with a later update; the app currently registers the "
                "integration and its allowed egress domains."
            ),
        ),
        endpoint_catalog=[],
    )
