from enum import Enum

from pydantic import BaseModel, field_validator

APPLICATION_NAME_MAX_LENGTH = 100
CUSTOM_CONTENT_MAX_LENGTH = 10_000
CUSTOM_NAV_ITEMS_MAX_COUNT = 20
HEX_COLOR_MAX_LENGTH = 9  # e.g. "#RRGGBBAA"


class LogoDisplayStyle(str, Enum):
    LOGO_AND_NAME = "logo_and_name"
    LOGO_ONLY = "logo_only"
    NAME_ONLY = "name_only"


class NavigationItem(BaseModel):
    link: str
    icon: str | None = None
    svg_logo: str | None = None
    title: str


class EnterpriseSettingsSnapshot(BaseModel):
    """Workspace-wide white-label settings as persisted in the KV store.

    The `*_filename` fields are internal: they name the file-store objects
    holding the uploaded image assets and are stripped from the API response
    (the frontend fetches assets through the image endpoints instead).
    """

    application_name: str | None = None
    use_custom_logo: bool = False
    use_custom_logotype: bool = False
    use_custom_logo_dark: bool = False
    use_custom_logotype_dark: bool = False
    use_custom_favicon: bool = False
    logo_display_style: LogoDisplayStyle | None = None

    # Light customization on top of the logo/name: brand colors override the
    # theme primary at runtime; email_cta_color recolors the email template.
    brand_color: str | None = None
    brand_color_dark: str | None = None
    email_cta_color: str | None = None

    # Custom navigation entries rendered in the app sidebar.
    custom_nav_items: list[NavigationItem] = []

    # Custom text surfaces consumed by the existing frontend hooks.
    custom_lower_disclaimer_content: str | None = None
    custom_header_content: str | None = None
    two_lines_for_chat_header: bool | None = None
    custom_popup_header: str | None = None
    custom_popup_content: str | None = None
    enable_consent_screen: bool | None = None
    consent_screen_prompt: str | None = None
    show_first_visit_notice: bool | None = None
    custom_greeting_message: str | None = None
    custom_login_subtitle: str | None = None
    custom_help_link_url: str | None = None
    custom_help_link_label: str | None = None
    hide_onyx_branding: bool | None = None

    # Internal: file-store ids of the uploaded brand assets.
    logo_filename: str | None = None
    logo_filename_dark: str | None = None
    logotype_filename: str | None = None
    logotype_filename_dark: str | None = None
    favicon_filename: str | None = None

    # Served only through the dedicated custom-analytics-script endpoint, so
    # the script source is not part of the general settings payload.
    custom_analytics_script: str | None = None

    @field_validator("application_name")
    @classmethod
    def validate_application_name(cls, value: str | None) -> str | None:
        if value is not None and len(value) > APPLICATION_NAME_MAX_LENGTH:
            raise ValueError(
                f"Application name must be at most {APPLICATION_NAME_MAX_LENGTH} characters"
            )
        return value

    @field_validator("brand_color", "brand_color_dark", "email_cta_color")
    @classmethod
    def validate_hex_color(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not value.startswith("#") or len(value) > HEX_COLOR_MAX_LENGTH:
            raise ValueError(f"Invalid hex color: {value}")
        try:
            int(value[1:], 16)
        except ValueError:
            raise ValueError(f"Invalid hex color: {value}") from None
        return value

    @field_validator(
        "custom_lower_disclaimer_content",
        "custom_header_content",
        "custom_popup_header",
        "custom_popup_content",
        "consent_screen_prompt",
        "custom_greeting_message",
        "custom_login_subtitle",
        "custom_help_link_url",
        "custom_help_link_label",
    )
    @classmethod
    def validate_custom_content(cls, value: str | None) -> str | None:
        if value is not None and len(value) > CUSTOM_CONTENT_MAX_LENGTH:
            raise ValueError(
                f"Custom content must be at most {CUSTOM_CONTENT_MAX_LENGTH} characters"
            )
        return value

    @field_validator("custom_nav_items")
    @classmethod
    def validate_nav_items(cls, value: list[NavigationItem]) -> list[NavigationItem]:
        if len(value) > CUSTOM_NAV_ITEMS_MAX_COUNT:
            raise ValueError(
                f"At most {CUSTOM_NAV_ITEMS_MAX_COUNT} custom navigation items are allowed"
            )
        return value

    @field_validator("custom_analytics_script")
    @classmethod
    def validate_analytics_script(cls, value: str | None) -> str | None:
        if value is not None and len(value) > 50_000:
            raise ValueError("Custom analytics script must be at most 50000 characters")
        return value


class RuntimeEnterpriseSettings(BaseModel):
    """The subset of enterprise settings resolvable without a request context
    (email sending, server startup). `load_runtime_settings` in `store.py`
    builds this; email code resolves it via `fetch_versioned_implementation`."""

    application_name: str | None = None
    email_cta_color: str | None = None
