"""Unit tests for the IM ``/场景`` scenario trigger: command parsing,
longest-name matching, permission-by-visibility, and the launch path."""

import uuid
from dataclasses import dataclass
from typing import Any, cast
from unittest.mock import patch

from sqlalchemy.orm import Session

from onyx.onyxbot.china import scenario_trigger
from onyx.onyxbot.china.scenario_trigger import (
    _split_name_and_payload,
    parse_scenario_command,
    try_scenario_trigger,
)

# ── parsing ────────────────────────────────────────────────────────────────


def test_parse_accepts_both_command_spellings() -> None:
    assert parse_scenario_command("/场景 财税风控 分析A公司") == "财税风控 分析A公司"
    assert parse_scenario_command("/scenario finance-tax 分析") == "finance-tax 分析"
    assert parse_scenario_command("  /场景  名称  ") == "名称"


def test_parse_rejects_non_commands() -> None:
    assert parse_scenario_command("你好") is None
    assert parse_scenario_command("/场景") == ""
    assert parse_scenario_command("请/场景 运行") is None


# ── name resolution ────────────────────────────────────────────────────────


def test_split_exact_name_wins_without_payload() -> None:
    assert _split_name_and_payload("财税风控", ["财税风控", "财税风控-月度"]) == (
        "财税风控",
        "",
    )


def test_split_longest_name_with_spaces_wins() -> None:
    names = ["财税", "财税 风控"]
    assert _split_name_and_payload("财税 风控 分析A公司", names) == (
        "财税 风控",
        "分析A公司",
    )


def test_split_requires_boundary_after_name() -> None:
    assert _split_name_and_payload("财税风控X", ["财税风控"]) is None


# ── trigger flow ───────────────────────────────────────────────────────────


@dataclass
class _Scenario:
    name: str
    id: str = "sc-1"


class _User:
    id = "user-1"


def _trigger(text: str, scenarios: list[_Scenario]) -> str | None:
    with patch("onyx.db.scenario.list_scenarios_for_user", return_value=scenarios):
        return try_scenario_trigger(cast(Session, object()), _User(), text)


def test_non_command_falls_through_to_chat() -> None:
    assert _trigger("普通问题", [_Scenario("财税风控")]) is None


def test_bare_command_answers_usage() -> None:
    reply = _trigger("/场景", [_Scenario("财税风控")])
    assert reply is not None and "/usage" in reply


def test_unknown_or_unauthorized_scenario_is_refused() -> None:
    reply = _trigger("/场景 私密场景 跑一下", [_Scenario("财税风控")])
    assert reply is not None
    assert "未找到" in reply
    # The visibility-filtered list is the permission check: the launch
    # path must never be reached for a name outside it.
    with patch("onyx.onyxbot.china.scenario_trigger._launch_job") as launch:
        _trigger("/场景 私密场景 跑一下", [])
        launch.assert_not_called()


def test_launches_job_and_returns_link() -> None:
    with (
        patch(
            "onyx.db.scenario.list_scenarios_for_user",
            return_value=[_Scenario("财税风控")],
        ),
        patch(
            "onyx.onyxbot.china.scenario_trigger._launch_job",
            return_value="/craft/v1?sessionId=s1",
        ) as launch,
    ):
        reply = try_scenario_trigger(
            cast(Session, object()), _User(), "/场景 财税风控 分析A公司"
        )
    launch.assert_called_once()
    assert reply is not None
    assert "任务已创建" in reply
    assert "/craft/v1?sessionId=s1" in reply


def test_launch_failure_degrades_to_a_reply_not_an_error() -> None:
    with (
        patch(
            "onyx.db.scenario.list_scenarios_for_user",
            return_value=[_Scenario("财税风控")],
        ),
        patch(
            "onyx.onyxbot.china.scenario_trigger._launch_job",
            side_effect=RuntimeError("boom"),
        ),
    ):
        reply = try_scenario_trigger(
            cast(Session, object()), _User(), "/场景 财税风控 分析"
        )
    assert reply is not None
    assert "失败" in reply


def test_launch_job_creates_session_and_job() -> None:
    class _BuildSession:
        id = str(uuid.uuid4())

    created: dict[str, Any] = {}

    class _Manager:
        def __init__(self, db: object) -> None:
            pass

        def create_session(self, **kwargs: object) -> _BuildSession:
            created.update(kwargs)
            return _BuildSession()

    def _fake_create_job_run(db: object, *, user: object, request: Any) -> None:
        del db, user
        # request is the real CraftJobCreateRequest; snapshot the fields the
        # IM path must set.
        created["job_request"] = {
            "prompt": request.prompt,
            "start": request.start,
            "scenario_id": str(request.scenario_id),
            "session_id": str(request.session_id),
        }

    scenario = _Scenario("财税风控")
    scenario.id = str(uuid.uuid4())

    class _Db:
        def commit(self) -> None:
            pass

    with (
        patch("onyx.server.features.build.session.manager.SessionManager", _Manager),
        patch(
            "onyx.server.features.build.jobs.api.create_job_run",
            _fake_create_job_run,
        ),
    ):
        link = scenario_trigger._launch_job(
            cast(Session, _Db()), user=_User(), scenario=scenario, prompt="分析A公司"
        )
    assert link == f"/craft/v1?sessionId={_BuildSession.id}"
    assert created["scenario_id"] == scenario.id
    assert created["name"] == "IM: 财税风控"
    job_request = created["job_request"]
    assert isinstance(job_request, dict)
    assert job_request["prompt"] == "分析A公司"
    assert job_request["start"] is True
