from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response

from onyx.auth.permissions import require_permission
from onyx.db.enums import Permission
from onyx.db.models import User
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.file_store.file_store import get_default_file_store
from onyx.server.enterprise_settings.models import EnterpriseSettingsSnapshot
from onyx.server.enterprise_settings.store import (
    delete_enterprise_image,
    enterprise_settings_write_lock,
    get_favicon_filename,
    load_enterprise_settings,
    save_enterprise_image,
    store_enterprise_settings,
)
from onyx.server.runtime.onyx_runtime import OnyxRuntime
from onyx.utils.audit import (
    AuditAction,
    AuditOutcome,
    actor_from_user,
    emit_audit_event,
)

basic_router = APIRouter(prefix="/enterprise-settings")
admin_router = APIRouter(prefix="/admin/enterprise-settings")

# Snapshot fields never exposed over the general settings payload. Filenames
# are managed exclusively by the upload/delete asset endpoints; the analytics
# script is served only through its dedicated endpoint.
_RESPONSE_EXCLUDED_FIELDS = frozenset(
    {
        "logo_filename",
        "logo_filename_dark",
        "logotype_filename",
        "logotype_filename_dark",
        "favicon_filename",
        "custom_analytics_script",
    }
)

# PATCH can never touch the asset filenames; they change only via uploads.
_NON_PATCHABLE_FIELDS = frozenset(
    {
        "logo_filename",
        "logo_filename_dark",
        "logotype_filename",
        "logotype_filename_dark",
        "favicon_filename",
    }
)

_MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024
_ALLOWED_IMAGE_TYPES = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/webp",
        "image/svg+xml",
        "image/x-icon",
        "image/vnd.microsoft.icon",
    }
)

# The branding read surface is public (see PUBLIC_ENDPOINT_SPECS in
# onyx/server/auth_check.py): the login page renders the enterprise name and
# logo before any authentication. Only the admin surface is authenticated.
_admin_auth = require_permission(Permission.FULL_ADMIN_PANEL_ACCESS)


def _enterprise_settings_response() -> dict:
    settings = load_enterprise_settings()
    return settings.model_dump(exclude=_RESPONSE_EXCLUDED_FIELDS)


def _apply_patch(patch: EnterpriseSettingsSnapshot, current_user: User) -> dict:
    # Validators already ran when FastAPI parsed the patch body; merging via
    # model_copy intentionally re-runs nothing. Only caller-sent fields change.
    update = {
        field: getattr(patch, field)
        for field in patch.model_fields_set
        if field not in _NON_PATCHABLE_FIELDS
    }
    with enterprise_settings_write_lock():
        existing = load_enterprise_settings()
        merged = existing.model_copy(update=update)
        store_enterprise_settings(merged)

    emit_audit_event(
        AuditAction.ENTERPRISE_SETTINGS_CHANGE,
        AuditOutcome.SUCCESS,
        actor=actor_from_user(current_user),
        resource_type="enterprise_settings",
        extra={"updated_fields": sorted(update.keys())},
    )
    return _enterprise_settings_response()


def _image_response(data: bytes, mime_type: str) -> Response:
    # no-cache: admins expect an uploaded logo to appear without manual cache
    # clearing; the frontend additionally cache-busters the URL.
    return Response(
        content=data,
        media_type=mime_type,
        headers={"Cache-Control": "no-cache"},
    )


def _validate_upload(file: UploadFile) -> tuple[bytes, str]:
    mime_type = file.content_type or ""
    if mime_type not in _ALLOWED_IMAGE_TYPES:
        raise OnyxError(
            OnyxErrorCode.INVALID_INPUT,
            f"Unsupported image type: {mime_type or 'unknown'}. "
            f"Allowed: {sorted(_ALLOWED_IMAGE_TYPES)}",
        )
    content = file.file.read()
    if not content:
        raise OnyxError(OnyxErrorCode.INVALID_INPUT, "Image file is empty")
    if len(content) > _MAX_IMAGE_SIZE_BYTES:
        raise OnyxError(
            OnyxErrorCode.INVALID_INPUT,
            f"Image must be at most {_MAX_IMAGE_SIZE_BYTES // (1024 * 1024)} MB",
        )
    return content, mime_type


def _upload_asset(
    field_name: str,
    enable_flag: str | None,
    file: UploadFile,
    current_user: User,
) -> dict:
    content, mime_type = _validate_upload(file)
    with enterprise_settings_write_lock():
        existing = load_enterprise_settings()
        previous_filename = getattr(existing, field_name)
        new_filename = save_enterprise_image(content, mime_type, file.filename)
        merged = existing.model_copy(
            update={
                field_name: new_filename,
                **({enable_flag: True} if enable_flag else {}),
            }
        )
        store_enterprise_settings(merged)
    if previous_filename and previous_filename != new_filename:
        delete_enterprise_image(previous_filename)

    emit_audit_event(
        AuditAction.ENTERPRISE_SETTINGS_CHANGE,
        AuditOutcome.SUCCESS,
        actor=actor_from_user(current_user),
        resource_type="enterprise_settings",
        extra={"asset": field_name, "action": "upload"},
    )
    return _enterprise_settings_response()


def _delete_asset(field_name: str, enable_flag: str | None, current_user: User) -> dict:
    with enterprise_settings_write_lock():
        existing = load_enterprise_settings()
        previous_filename = getattr(existing, field_name)
        update: dict = {field_name: None}
        if enable_flag:
            update[enable_flag] = False
        merged = existing.model_copy(update=update)
        store_enterprise_settings(merged)
    if previous_filename:
        delete_enterprise_image(previous_filename)

    emit_audit_event(
        AuditAction.ENTERPRISE_SETTINGS_CHANGE,
        AuditOutcome.SUCCESS,
        actor=actor_from_user(current_user),
        resource_type="enterprise_settings",
        extra={"asset": field_name, "action": "delete"},
    )
    return _enterprise_settings_response()


@basic_router.get("")
def fetch_enterprise_settings() -> dict:
    return _enterprise_settings_response()


@basic_router.get("/logo")
def fetch_logo() -> Response:
    onyx_file = OnyxRuntime.get_logo()
    return _image_response(onyx_file.data, onyx_file.mime_type)


@basic_router.get("/logo-dark")
def fetch_logo_dark() -> Response:
    onyx_file = OnyxRuntime.get_logo(dark=True)
    return _image_response(onyx_file.data, onyx_file.mime_type)


@basic_router.get("/logotype")
def fetch_logotype() -> Response:
    onyx_file = OnyxRuntime.get_logotype()
    return _image_response(onyx_file.data, onyx_file.mime_type)


@basic_router.get("/logotype-dark")
def fetch_logotype_dark() -> Response:
    onyx_file = OnyxRuntime.get_logotype(dark=True)
    return _image_response(onyx_file.data, onyx_file.mime_type)


@basic_router.get("/favicon")
def fetch_favicon() -> Response:
    filename = get_favicon_filename()
    # The frontend serves the default /onyx.ico itself; this endpoint only
    # exists for uploaded favicons.
    if not filename:
        raise OnyxError(OnyxErrorCode.NOT_FOUND, "No custom favicon uploaded")
    onyx_file = get_default_file_store().get_file_with_mime_type(filename)
    if not onyx_file:
        raise OnyxError(
            OnyxErrorCode.NOT_FOUND, "Custom favicon missing from file store"
        )
    return _image_response(onyx_file.data, onyx_file.mime_type)


@basic_router.get("/custom-analytics-script")
def fetch_custom_analytics_script() -> str | None:
    # Public like the rest of the branding surface; the frontend only ever
    # injects the script for authenticated users.
    return load_enterprise_settings().custom_analytics_script


@admin_router.patch("")
def admin_patch_enterprise_settings(
    patch: EnterpriseSettingsSnapshot,
    current_user: User = Depends(_admin_auth),
) -> dict:
    return _apply_patch(patch, current_user)


@admin_router.put("/logo")
def admin_upload_logo(
    file: UploadFile = File(...),
    current_user: User = Depends(_admin_auth),
) -> dict:
    return _upload_asset("logo_filename", "use_custom_logo", file, current_user)


@admin_router.delete("/logo")
def admin_delete_logo(current_user: User = Depends(_admin_auth)) -> dict:
    return _delete_asset("logo_filename", "use_custom_logo", current_user)


@admin_router.put("/logo-dark")
def admin_upload_logo_dark(
    file: UploadFile = File(...),
    current_user: User = Depends(_admin_auth),
) -> dict:
    return _upload_asset(
        "logo_filename_dark", "use_custom_logo_dark", file, current_user
    )


@admin_router.delete("/logo-dark")
def admin_delete_logo_dark(current_user: User = Depends(_admin_auth)) -> dict:
    return _delete_asset("logo_filename_dark", "use_custom_logo_dark", current_user)


@admin_router.put("/logotype")
def admin_upload_logotype(
    file: UploadFile = File(...),
    current_user: User = Depends(_admin_auth),
) -> dict:
    return _upload_asset("logotype_filename", "use_custom_logotype", file, current_user)


@admin_router.delete("/logotype")
def admin_delete_logotype(current_user: User = Depends(_admin_auth)) -> dict:
    return _delete_asset("logotype_filename", "use_custom_logotype", current_user)


@admin_router.put("/logotype-dark")
def admin_upload_logotype_dark(
    file: UploadFile = File(...),
    current_user: User = Depends(_admin_auth),
) -> dict:
    return _upload_asset(
        "logotype_filename_dark", "use_custom_logotype_dark", file, current_user
    )


@admin_router.delete("/logotype-dark")
def admin_delete_logotype_dark(current_user: User = Depends(_admin_auth)) -> dict:
    return _delete_asset(
        "logotype_filename_dark", "use_custom_logotype_dark", current_user
    )


@admin_router.put("/favicon")
def admin_upload_favicon(
    file: UploadFile = File(...),
    current_user: User = Depends(_admin_auth),
) -> dict:
    return _upload_asset("favicon_filename", "use_custom_favicon", file, current_user)


@admin_router.delete("/favicon")
def admin_delete_favicon(current_user: User = Depends(_admin_auth)) -> dict:
    return _delete_asset("favicon_filename", "use_custom_favicon", current_user)
