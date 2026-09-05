from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from onyx.db.enums import ScenarioAccessLevel
from onyx.db.scenario import access_level_for_scenario, copy_scenario_name


def test_copy_scenario_name_keeps_short_names() -> None:
    assert copy_scenario_name("合规风险预警") == "合规风险预警 (copy)"


def test_copy_scenario_name_fits_max_length() -> None:
    name = "x" * 128
    copied = copy_scenario_name(name)
    assert len(copied) == 128
    assert copied.endswith(" (copy)")


def test_admin_owns_workspace_pack(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "onyx.db.scenario.has_global_permission",
        lambda _user, _permission: True,
    )
    scenario = SimpleNamespace(author_user_id=None, public_permission="VIEWER")
    user = SimpleNamespace(id=uuid4())
    db_session = MagicMock()

    assert (
        access_level_for_scenario(db_session, scenario, user)
        == ScenarioAccessLevel.OWNER
    )
    db_session.scalar.assert_not_called()


def test_non_admin_views_workspace_pack(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "onyx.db.scenario.has_global_permission",
        lambda _user, _permission: False,
    )
    scenario = SimpleNamespace(
        id=uuid4(),
        author_user_id=None,
        public_permission="VIEWER",
    )
    user = SimpleNamespace(id=uuid4())
    db_session = MagicMock()
    db_session.scalar.return_value = None
    db_session.scalars.return_value.all.return_value = []

    assert (
        access_level_for_scenario(db_session, scenario, user)
        == ScenarioAccessLevel.VIEWER
    )


def test_author_remains_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = uuid4()
    monkeypatch.setattr(
        "onyx.db.scenario.has_global_permission",
        lambda _user, _permission: False,
    )
    scenario = SimpleNamespace(author_user_id=user_id, public_permission=None)
    user = SimpleNamespace(id=user_id)

    assert (
        access_level_for_scenario(MagicMock(), scenario, user)
        == ScenarioAccessLevel.OWNER
    )
