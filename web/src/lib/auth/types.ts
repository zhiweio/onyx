// Wire values of the backend session-rejection codes carried in the `/api/me`
// 403 body (`backend/onyx/error_handling/error_codes.py`).
export enum SessionEndReason {
  EXPIRED = "SESSION_EXPIRED",
  TERMINATED = "SESSION_TERMINATED",
  UNRECOGNIZED = "SESSION_UNRECOGNIZED",
}

// Mirrors backend onyx.db.enums.SSOProviderType. The China workplace platform
// values flow through /auth/type even though the union here was historically
// Google/OIDC/SAML only.
export type SSOProviderType =
  | "GOOGLE_OAUTH"
  | "OIDC"
  | "SAML"
  | "WECOM"
  | "DINGTALK"
  | "FEISHU"
  | "WPS365";

export interface SSOProviderOption {
  name: string;
  displayName: string;
  providerType: SSOProviderType;
  authorizeUrl: string;
}

export interface AuthTypeMetadata {
  multiTenant: boolean;
  requiresVerification: boolean;
  anonymousUserEnabled: boolean | null;
  passwordMinLength: number;
  passwordMaxLength: number;
  passwordRequireUppercase: boolean;
  passwordRequireLowercase: boolean;
  passwordRequireDigit: boolean;
  passwordRequireSpecialChar: boolean;
  hasUsers: boolean;
  oauthEnabled: boolean;
  // Admin kill switch (single-tenant). False hides password login and signup.
  passwordAuthEnabled: boolean;
  // Enabled DB-backed SSO providers, one login button each. Empty on cloud
  // and when no provider rows exist.
  ssoProviders?: SSOProviderOption[];
}
