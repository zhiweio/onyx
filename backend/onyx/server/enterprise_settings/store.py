from collections.abc import Iterator
from contextlib import contextmanager
from io import BytesIO

from onyx.cache.locks import cache_shared_lock
from onyx.configs.constants import KV_ENTERPRISE_SETTINGS_KEY, FileOrigin
from onyx.file_store.file_store import get_default_file_store
from onyx.key_value_store.factory import get_kv_store
from onyx.key_value_store.interface import KvKeyNotFoundError
from onyx.server.enterprise_settings.models import (
    EnterpriseSettingsSnapshot,
    RuntimeEnterpriseSettings,
)
from onyx.utils.logger import setup_logger
from shared_configs.contextvars import get_current_tenant_id

logger = setup_logger()

_ENTERPRISE_SETTINGS_WRITE_LOCK_TIMEOUT_S = 10.0


@contextmanager
def enterprise_settings_write_lock() -> Iterator[None]:
    """Serialize read-modify-write of the enterprise settings record so
    concurrent admin PATCHes cannot each merge onto a stale snapshot. Same
    pattern as the general settings write lock."""
    with cache_shared_lock(
        lock_name=f"enterprise_settings_write:{get_current_tenant_id()}",
        max_time_lock_held_s=_ENTERPRISE_SETTINGS_WRITE_LOCK_TIMEOUT_S,
        wait_for_lock_s=_ENTERPRISE_SETTINGS_WRITE_LOCK_TIMEOUT_S,
        logger=logger,
    ):
        yield


def load_enterprise_settings() -> EnterpriseSettingsSnapshot:
    kv_store = get_kv_store()
    try:
        stored = kv_store.load(KV_ENTERPRISE_SETTINGS_KEY)
    except KvKeyNotFoundError:
        return EnterpriseSettingsSnapshot()
    except Exception:
        logger.exception("Error loading enterprise settings from KV store")
        return EnterpriseSettingsSnapshot()

    try:
        return (
            EnterpriseSettingsSnapshot.model_validate(stored)
            if stored
            else EnterpriseSettingsSnapshot()
        )
    except Exception:
        # A malformed snapshot must never take the login page down; degrade to
        # default branding and surface the error in the logs.
        logger.exception("Stored enterprise settings are invalid; using defaults")
        return EnterpriseSettingsSnapshot()


def store_enterprise_settings(settings: EnterpriseSettingsSnapshot) -> None:
    get_kv_store().store(KV_ENTERPRISE_SETTINGS_KEY, settings.model_dump())


def load_runtime_settings() -> RuntimeEnterpriseSettings:
    """Runtime branding values for request-less contexts (email sending).
    Email code resolves this via `fetch_versioned_implementation`, so the
    signature must stay `() -> object with .application_name`."""
    settings = load_enterprise_settings()
    return RuntimeEnterpriseSettings(
        application_name=settings.application_name,
        email_cta_color=settings.email_cta_color,
    )


def get_logo_filename(dark: bool = False) -> str | None:
    """File-store id of the custom logo. The dark variant falls back to the
    light asset when no dark logo was uploaded, so callers need no fallback
    logic of their own."""
    settings = load_enterprise_settings()
    if dark:
        return settings.logo_filename_dark or settings.logo_filename
    return settings.logo_filename


def get_logotype_filename(dark: bool = False) -> str | None:
    settings = load_enterprise_settings()
    if dark:
        return settings.logotype_filename_dark or settings.logotype_filename
    return settings.logotype_filename


def get_favicon_filename() -> str | None:
    return load_enterprise_settings().favicon_filename


def save_enterprise_image(
    content: bytes, mime_type: str, display_name: str | None
) -> str:
    """Persist an uploaded brand asset and return its file-store id."""
    return get_default_file_store().save_file(
        BytesIO(content),
        display_name,
        FileOrigin.BRANDING,
        mime_type,
    )


def delete_enterprise_image(file_id: str) -> None:
    try:
        get_default_file_store().delete_file(file_id, error_on_missing=False)
    except Exception:
        # Orphaned blobs are harmless; never block a branding reset on cleanup.
        logger.warning("Failed to delete branding asset %s", file_id)
