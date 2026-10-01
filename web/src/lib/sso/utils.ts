import { SvgGlobe, SvgUserKey } from "@opal/icons";
import {
  SvgDingTalk,
  SvgFeishu,
  SvgGoogle,
  SvgWeCom,
  SvgWps365,
} from "@opal/logos";
import type { IconFunctionComponent } from "@opal/types";
import { toast } from "@opal/layouts";
import { SSOProviderType } from "@/lib/sso/interfaces";

interface SSOProviderDetail {
  label: string;
  icon: IconFunctionComponent;
  description: string;
}

export const SSO_PROVIDER_DETAILS: Record<SSOProviderType, SSOProviderDetail> =
  {
    GOOGLE_OAUTH: {
      label: "Google",
      icon: SvgGoogle,
      description: "Use Google as the identity provider.",
    },
    OIDC: {
      label: "OIDC",
      icon: SvgGlobe,
      description: "Connect a generic OpenID Connect provider.",
    },
    SAML: {
      label: "SAML",
      icon: SvgUserKey,
      description: "Connect a SAML identity provider.",
    },
    WECOM: {
      label: "WeCom",
      icon: SvgWeCom,
      description: "WeCom (企业微信) QR-code login and org-structure sync.",
    },
    DINGTALK: {
      label: "DingTalk",
      icon: SvgDingTalk,
      description: "DingTalk (钉钉) QR-code login and org-structure sync.",
    },
    FEISHU: {
      label: "Feishu",
      icon: SvgFeishu,
      description: "Feishu (飞书) auth-code login and org-structure sync.",
    },
    WPS365: {
      label: "WPS365",
      icon: SvgWps365,
      description: "WPS 365 OAuth2 login on the regional account endpoint.",
    },
  };

// Provider types the create modal offers, in dropdown order.
export const CREATABLE_SSO_PROVIDER_TYPES: SSOProviderType[] = [
  "GOOGLE_OAUTH",
  "OIDC",
  "SAML",
  "WECOM",
  "DINGTALK",
  "FEISHU",
  "WPS365",
];

export type SSOConfigFieldKind =
  | "text"
  | "textarea"
  | "password"
  | "switch"
  | "chips";

// One entry per admin-editable key in a provider type's backend config model.
// `name` must match the backend config field exactly, since values are sent
// as config.<name>.
export interface SSOConfigField {
  name: string;
  label: string;
  kind: SSOConfigFieldKind;
  description: string;
  optional?: boolean;
  placeholder?: string;
}

const CLIENT_ID_FIELD: SSOConfigField = {
  name: "client_id",
  label: "Client ID",
  kind: "text",
  description: "The OAuth client ID from your provider's console.",
  placeholder: "Client ID",
};
const CLIENT_SECRET_FIELD: SSOConfigField = {
  name: "client_secret",
  label: "Client Secret",
  kind: "password",
  description: "The OAuth client secret. Stored encrypted.",
  placeholder: "Client secret",
};
const PKCE_FIELD: SSOConfigField = {
  name: "pkce_enabled",
  label: "Enable PKCE",
  kind: "switch",
  description:
    "Send a PKCE code challenge with this provider's login flow. " +
    "A deployment-wide setting may force this on.",
};
const SCOPES_FIELD: SSOConfigField = {
  name: "scopes",
  label: "Scopes",
  kind: "chips",
  optional: true,
  description:
    "Override the OAuth scopes requested at login. " +
    "Empty uses the deployment defaults.",
  placeholder: "Add a scope (e.g. openid)",
};

const EMAIL_DOMAIN_FIELD: SSOConfigField = {
  name: "email_domain",
  label: "Email Domain",
  kind: "text",
  description:
    "Builds a deterministic login email when the platform does not return " +
    "one, e.g. account_id@this-domain. Use your company domain.",
  placeholder: "corp.example.com",
};

export const CONFIG_FIELDS_BY_TYPE: Record<SSOProviderType, SSOConfigField[]> =
  {
    GOOGLE_OAUTH: [
      CLIENT_ID_FIELD,
      CLIENT_SECRET_FIELD,
      PKCE_FIELD,
      SCOPES_FIELD,
    ],
    OIDC: [
      CLIENT_ID_FIELD,
      CLIENT_SECRET_FIELD,
      {
        name: "openid_config_url",
        label: "OpenID Configuration URL",
        kind: "text",
        description: "The IdP's OpenID Connect discovery document URL.",
        placeholder: "https://example.com/.well-known/openid-configuration",
      },
      {
        name: "require_verified_email",
        label: "Require Verified Email Claim",
        kind: "switch",
        description:
          "Reject sign-ins when the IdP omits the optional email_verified " +
          "claim. Leave off for IdPs that do not send it, such as " +
          "Microsoft Entra ID.",
      },
      PKCE_FIELD,
      SCOPES_FIELD,
    ],
    SAML: [
      {
        name: "idp_entity_id",
        label: "IdP Entity ID",
        kind: "text",
        description: "The identity provider's entity ID (issuer).",
        placeholder: "https://idp.example.com/entity",
      },
      {
        name: "idp_sso_url",
        label: "IdP SSO URL",
        kind: "text",
        description: "The IdP endpoint that receives sign-in requests.",
        placeholder: "https://idp.example.com/sso",
      },
      {
        name: "idp_x509_cert",
        label: "IdP X.509 Certificate",
        kind: "textarea",
        description:
          "The IdP's signing certificate, used to verify assertions.",
        placeholder: "-----BEGIN CERTIFICATE-----",
      },
      {
        name: "sp_entity_id",
        label: "SP Entity ID",
        kind: "text",
        description: "This instance's entity ID, registered with the IdP.",
        placeholder: "onyx",
      },
      {
        name: "sp_x509_cert",
        label: "SP X.509 Certificate",
        kind: "textarea",
        description:
          "Only if this instance signs requests or decrypts assertions.",
        optional: true,
        placeholder: "-----BEGIN CERTIFICATE-----",
      },
      {
        name: "sp_private_key",
        label: "SP Private Key",
        kind: "password",
        description:
          "Private key paired with the SP certificate. Stored encrypted.",
        optional: true,
        placeholder: "-----BEGIN PRIVATE KEY-----",
      },
      {
        name: "email_attribute",
        label: "Email Attribute",
        kind: "text",
        description:
          "SAML attribute holding the user's email. Defaults to common keys.",
        optional: true,
        placeholder: "email",
      },
    ],
    WECOM: [
      EMAIL_DOMAIN_FIELD,
      {
        name: "corp_id",
        label: "Corp ID",
        kind: "text",
        description: "WeCom enterprise ID (企业ID), from the admin console.",
        placeholder: "ww**************",
      },
      {
        name: "corp_secret",
        label: "Corp Secret",
        kind: "password",
        description: "The self-built app's secret. Stored encrypted.",
        placeholder: "Corp secret",
      },
      {
        name: "agent_id",
        label: "Agent ID",
        kind: "text",
        description: "The self-built app's agent ID (应用AgentId).",
        placeholder: "1000002",
      },
      {
        name: "bot_token",
        label: "IM Bot Token",
        kind: "password",
        description:
          "WeCom callback-mode token. Set to also enable the WeCom IM bot.",
        optional: true,
        placeholder: "Callback token",
      },
      {
        name: "bot_encoding_aes_key",
        label: "IM Bot EncodingAESKey",
        kind: "password",
        description: "WeCom callback-mode message key. Stored encrypted.",
        optional: true,
        placeholder: "EncodingAESKey",
      },
    ],
    DINGTALK: [
      EMAIL_DOMAIN_FIELD,
      CLIENT_ID_FIELD,
      CLIENT_SECRET_FIELD,
      {
        name: "robot_code",
        label: "Robot Code",
        kind: "text",
        description:
          "DingTalk robot code. Set to also enable the DingTalk IM bot.",
        optional: true,
        placeholder: "Robot code",
      },
      {
        name: "bot_aes_key",
        label: "IM Bot AES Key",
        kind: "password",
        description: "DingTalk event-stream AES key. Stored encrypted.",
        optional: true,
        placeholder: "AES key",
      },
    ],
    FEISHU: [
      EMAIL_DOMAIN_FIELD,
      {
        name: "app_id",
        label: "App ID",
        kind: "text",
        description: "Feishu app ID (应用 App ID) from the developer console.",
        placeholder: "cli_a********",
      },
      {
        name: "app_secret",
        label: "App Secret",
        kind: "password",
        description: "The Feishu app secret. Stored encrypted.",
        placeholder: "App secret",
      },
      {
        name: "bot_verification_token",
        label: "IM Bot Verification Token",
        kind: "password",
        description:
          "Feishu event verification token. Set to also enable the Feishu IM bot.",
        optional: true,
        placeholder: "Verification token",
      },
      {
        name: "bot_encrypt_key",
        label: "IM Bot Encrypt Key",
        kind: "password",
        description: "Feishu event encryption key. Stored encrypted.",
        optional: true,
        placeholder: "Encrypt key",
      },
    ],
    WPS365: [
      EMAIL_DOMAIN_FIELD,
      CLIENT_ID_FIELD,
      CLIENT_SECRET_FIELD,
      {
        name: "base_url",
        label: "Account Base URL",
        kind: "text",
        description:
          "WPS 365 account-service base URL. The default fits the " +
          "regional (cn) deployment.",
        optional: true,
        placeholder: "https://account.wps.cn",
      },
    ],
  };

export async function copyRedirectUri(redirectUri: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(redirectUri);
    toast.success("Redirect URI copied");
  } catch {
    toast.error("Could not copy");
  }
}
