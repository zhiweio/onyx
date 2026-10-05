"""IM ``/场景`` command: launch a CraftJob for a scenario from chat.

Dispatch runs before the normal chat turn: when the message starts with
``/场景`` (or ``/scenario``), the command resolves the scenario by name
among the ones visible to the IM user — visibility *is* the permission
check — creates a BuildSession, and starts the job through the same
``create_job_run`` kernel the REST endpoint uses. The platform reply is
the run link; normal chat never sees command messages.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from onyx.utils.logger import setup_logger

logger = setup_logger()

SCENARIO_COMMANDS = ("/场景", "/scenario")


def parse_scenario_command(text: str) -> str | None:
    """Return the command payload for a ``/场景`` message, else ``None``.

    Name/payload splitting is deferred: scenario names may contain spaces,
    so the longest-match against the visible scenario list decides where
    the name ends."""
    stripped = text.strip()
    for command in SCENARIO_COMMANDS:
        if not stripped.startswith(command):
            continue
        return stripped[len(command) :].strip()
    return None


def _split_name_and_payload(
    rest: str, scenario_names: list[str]
) -> tuple[str, str] | None:
    """Longest-prefix match of the command payload against scenario names.

    Exact match wins; otherwise the longest name that prefixes the payload
    (followed by end-of-string or whitespace) is used, so names with spaces
    resolve and the remainder becomes the job prompt."""
    exact = next((name for name in scenario_names if rest == name), None)
    if exact is not None:
        return exact, ""
    matches = [
        name
        for name in scenario_names
        if rest.startswith(name) and rest[len(name) : len(name) + 1].isspace()
    ]
    if not matches:
        return None
    name = max(matches, key=len)
    return name, rest[len(name) :].strip()


def try_scenario_trigger(db_session: Session, user: Any, text: str) -> str | None:
    """Handle a ``/场景`` message end-to-end.

    Returns the platform reply when the message was a scenario command
    (including the not-found/no-permission case); ``None`` lets the caller
    fall through to a normal chat turn."""
    payload_text = parse_scenario_command(text)
    if payload_text is None:
        return None
    if not payload_text:
        return _usage_reply()

    from onyx.db.scenario import list_scenarios_for_user

    scenarios = list_scenarios_for_user(db_session, user)
    split = _split_name_and_payload(payload_text, [s.name for s in scenarios])
    if split is None:
        return _not_found_reply()
    name, payload = split
    scenario = next(s for s in scenarios if s.name == name)

    from onyx.db.craft_job import list_open_craft_jobs_for_user
    from onyx.db.enums import SessionOrigin
    from onyx.server.settings.store import load_settings

    open_jobs = list_open_craft_jobs_for_user(
        db_session, user.id, origin=SessionOrigin.IM
    )
    limit = load_settings().im_craft_job_concurrency_limit
    if len(open_jobs) >= limit:
        return _limit_reached_reply(open_jobs)

    try:
        link, session_id = _launch_job(
            db_session, user=user, scenario=scenario, prompt=payload
        )
    except Exception:
        logger.exception("IM scenario trigger failed for %s", name)
        return (
            f"场景「{name}」启动失败,请稍后重试或在 Web 端启动。"
            "\nFailed to start the scenario; retry later or use the web UI."
        )
    return (
        f"任务已创建:场景「{name}」。\n"
        f"[打开任务]({link})\nsessionId: {session_id}\n\n"
        "任务完成或失败会自动通知你;/我的任务 查看运行中的任务。"
    )


def craft_job_link(session_id: Any) -> str:
    """Full web URL of a Craft session — IM cards render it as a clickable
    link that opens in the browser."""
    from onyx.configs.app_configs import WEB_DOMAIN

    return f"{WEB_DOMAIN}/craft/v1?sessionId={session_id}"


def im_job_display_name(name: str) -> str:
    """Job name minus the launcher prefix — the scenario name reads better
    as link text than ``IM: 税务合规体检``."""
    return name[len("IM: ") :] if name.startswith("IM: ") else name


def _limit_reached_reply(open_jobs: list[Any]) -> str:
    """Rejection card when the user's IM job concurrency is exhausted:
    list what is running so the message doubles as a status view."""
    from onyx.db.enums import CraftJobStatus

    status_labels = {
        CraftJobStatus.PENDING: "排队中",
        CraftJobStatus.RUNNING: "运行中",
        CraftJobStatus.WAITING_LANES: "运行中",
        CraftJobStatus.INTERRUPTED: "待处理(需在网页端确认)",
    }
    lines = []
    for idx, job in enumerate(open_jobs, start=1):
        label = status_labels.get(job.status, job.status.value)
        display = im_job_display_name(job.name)
        lines.append(
            f"{idx}. [{display}]({craft_job_link(job.session_id)}) — {label}"
            f"\n   sessionId: {job.session_id}"
        )
    listing = "\n".join(lines)
    return (
        f"⚠️ 你已有 {len(open_jobs)} 个场景任务在运行,暂时无法启动新任务。"
        f"\n{listing}\n\n"
        "点击任务名可在浏览器打开;任务完成会自动通知你;"
        "用 /我的任务 查看,/取消任务 <序号> 可取消并释放额度。"
    )


def _launch_job(
    db_session: Session, *, user: Any, scenario: Any, prompt: str
) -> tuple[str, str]:
    from onyx.db.enums import SessionOrigin
    from onyx.server.features.build.jobs.api import create_job_run
    from onyx.server.features.build.jobs.models import CraftJobCreateRequest
    from onyx.server.features.build.session.manager import SessionManager

    goal = prompt.strip() or f"Run scenario: {scenario.name}"
    session_manager = SessionManager(db_session)
    build_session = session_manager.create_session(
        user_id=user.id,
        name=f"IM: {scenario.name}",
        scenario_id=scenario.id,
        origin=SessionOrigin.IM,
    )
    db_session.commit()
    create_job_run(
        db_session,
        user=user,
        request=CraftJobCreateRequest(
            session_id=build_session.id,
            scenario_id=scenario.id,
            name=f"IM: {scenario.name}",
            prompt=goal,
            start=True,
        ),
    )
    return craft_job_link(build_session.id), str(build_session.id)


def _usage_reply() -> str:
    return "用法 /usage: /场景 <名称> <任务内容> | /scenario <name> <task>"


def _not_found_reply() -> str:
    return (
        "未找到该场景,或你没有使用权限。请确认场景名称;"
        "场景由管理员在广场配置。"
        "\nScenario not found or not shared with you."
    )
