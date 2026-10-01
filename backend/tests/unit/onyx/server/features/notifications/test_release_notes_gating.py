from unittest.mock import patch

from onyx.db.models import User
from onyx.server.features.notifications.api import _check_for_notifications_to_create


def _make_user() -> User:
    return User(id="00000000-0000-0000-0000-000000000000", email="a@b.co")


def test_release_notes_check_skipped_when_disabled() -> None:
    user = _make_user()
    with (
        patch(
            "onyx.server.features.notifications.api.ENABLE_RELEASE_NOTES_NOTIFICATIONS",
            False,
        ),
        patch(
            "onyx.server.features.notifications.api.ensure_release_notes_fresh_and_notify"
        ) as release_notes_check,
        patch(
            "onyx.server.features.notifications.api.ensure_build_mode_intro_notification"
        ),
        patch(
            "onyx.server.features.notifications.api.ensure_permissions_migration_notification"
        ),
    ):
        _check_for_notifications_to_create(user, None)  # type: ignore[arg-type]

    release_notes_check.assert_not_called()


def test_release_notes_check_runs_when_enabled() -> None:
    user = _make_user()
    with (
        patch(
            "onyx.server.features.notifications.api.ENABLE_RELEASE_NOTES_NOTIFICATIONS",
            True,
        ),
        patch(
            "onyx.server.features.notifications.api.ensure_release_notes_fresh_and_notify"
        ) as release_notes_check,
        patch(
            "onyx.server.features.notifications.api.ensure_build_mode_intro_notification"
        ),
        patch(
            "onyx.server.features.notifications.api.ensure_permissions_migration_notification"
        ),
    ):
        _check_for_notifications_to_create(user, None)  # type: ignore[arg-type]

    release_notes_check.assert_called_once()
