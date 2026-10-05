"""The WeCom provider catalog: the CLI gateway surface resolves to exactly
one action per request across every service (calendar, chat, contact, disk,
doc, mail, media, message, meeting, sheet, smartpage, smartsheet, todo,
identity) plus the transport endpoints, and default policies follow the
design (reads auto-approve; writes require approval; deletes, cancellations,
and the token bootstrap are denied)."""

from __future__ import annotations

import pytest

from onyx.db.enums import EndpointPolicy, ExternalAppType
from onyx.external_apps.matching.request import MatchContext, ProxiedRequest
from onyx.external_apps.matching.rules import rule_matches
from onyx.external_apps.providers.actions import RestRoute
from onyx.external_apps.providers.registry import get_endpoint_catalog
from onyx.external_apps.providers.wecom import WeComAction

_CATALOG = get_endpoint_catalog(ExternalAppType.WECOM)


def _matching_actions(method: str, path: str) -> set[str]:
    """Every catalog action whose rules recognise the request. Mirrors the
    gate evaluator: the query string is stripped before matching."""
    context = MatchContext(
        ProxiedRequest(method=method, path=path.split("?", 1)[0], body=None)
    )
    return {
        endpoint.id
        for endpoint in _CATALOG
        if any(rule_matches(rule, context) for rule in endpoint.matches)
    }


@pytest.mark.parametrize(
    "method, path, expected",
    [
        # Transport endpoints.
        (
            "POST",
            "/cgi-bin/aibot/cli/get_cli_config",
            {WeComAction.AUTH_BOOTSTRAP},
        ),
        (
            "POST",
            "/cli/service/discovery",
            {WeComAction.GATEWAY_DISCOVERY},
        ),
        ("POST", "/cli/task/query", {WeComAction.GATEWAY_TASK_QUERY}),
        ("POST", "/cli/file/upload", {WeComAction.GATEWAY_FILE_UPLOAD}),
        # Calendar.
        (
            "POST",
            "/cli/calendar/schedules/create",
            {WeComAction.CALENDAR_SCHEDULES_CREATE},
        ),
        (
            "POST",
            "/cli/calendar/schedules/cancel",
            {WeComAction.CALENDAR_SCHEDULES_CANCEL},
        ),
        (
            "POST",
            "/cli/calendar/schedules/free/list",
            {WeComAction.CALENDAR_SCHEDULES_FREE_LIST},
        ),
        # Chat — reads over conversations the robot sits in.
        ("POST", "/cli/chat/groups/list", {WeComAction.CHAT_GROUPS_LIST}),
        ("POST", "/cli/chat/messages/list", {WeComAction.CHAT_MESSAGES_LIST}),
        # Messages.
        ("POST", "/cli/message/send", {WeComAction.MESSAGE_SEND}),
        (
            "POST",
            "/cli/message/aibot/sessions/list",
            {WeComAction.MESSAGE_AIBOT_SESSIONS_LIST},
        ),
        # Docs & sheets.
        ("POST", "/cli/doc/search", {WeComAction.DOC_SEARCH}),
        ("POST", "/cli/doc/contents/get", {WeComAction.DOC_CONTENTS_GET}),
        (
            "POST",
            "/cli/doc/contents/overwrite",
            {WeComAction.DOC_CONTENTS_OVERWRITE},
        ),
        ("POST", "/cli/sheet/ranges/get", {WeComAction.SHEET_RANGES_GET}),
        (
            "POST",
            "/cli/sheet/subsheets/delete",
            {WeComAction.SHEET_SUBSHEETS_DELETE},
        ),
        # Smartsheet CRUD.
        ("POST", "/cli/smartsheet/records/add", {WeComAction.SMARTSHEET_RECORDS_ADD}),
        (
            "POST",
            "/cli/smartsheet/records/delete",
            {WeComAction.SMARTSHEET_RECORDS_DELETE},
        ),
        # Disk (drive), media, mail, identity.
        ("POST", "/cli/disk/files/download", {WeComAction.DISK_FILES_DOWNLOAD}),
        ("POST", "/cli/disk/folders/create", {WeComAction.DISK_FOLDERS_CREATE}),
        ("POST", "/cli/media/upload", {WeComAction.MEDIA_UPLOAD}),
        ("POST", "/cli/mail/send", {WeComAction.MAIL_SEND}),
        ("POST", "/cli/identity/whoami", {WeComAction.IDENTITY_WHOAMI}),
    ],
)
def test_route_resolution(method: str, path: str, expected: set[str]) -> None:
    assert _matching_actions(method, path) == expected


def test_query_string_is_ignored() -> None:
    assert _matching_actions("POST", "/cli/message/send?extra=1") == {
        WeComAction.MESSAGE_SEND
    }


def test_every_service_is_represented() -> None:
    ids = {endpoint.id for endpoint in _CATALOG}
    for prefix in (
        "wecom.calendar.",
        "wecom.chat.",
        "wecom.contact.",
        "wecom.disk.",
        "wecom.doc.",
        "wecom.mail.",
        "wecom.media.",
        "wecom.message.",
        "wecom.meeting.",
        "wecom.sheet.",
        "wecom.smartpage.",
        "wecom.smartsheet.",
        "wecom.todo.",
        "wecom.identity.",
        "wecom.gateway.",
    ):
        assert any(id.startswith(prefix) for id in ids), prefix


def test_paths_are_unique_across_catalog() -> None:
    """One exact path per action: a request can never be attributed to two
    different governing policies."""
    paths: list[tuple[str, str]] = []
    for endpoint in _CATALOG:
        route = endpoint.matches[0]
        assert isinstance(route, RestRoute)  # the WeCom catalog is REST-only
        assert "{" not in route.path  # exact paths only — the gateway is flat
        paths.append((route.method, route.path))
    assert len(paths) == len(set(paths))


def test_default_policies_follow_convention() -> None:
    """The gateway is POST-only, so the leaf verb decides: reads (get / list /
    search / query / download / whoami) are ALWAYS; deletes and cancellations
    are DENY; the token bootstrap is DENY (the proxy mints tokens server-side,
    never the agent); everything else is ASK."""
    read_leaves = {"get", "list", "search", "query", "download", "whoami"}
    deny_leaves = {"delete", "cancel"}
    by_id = {endpoint.id: endpoint for endpoint in _CATALOG}
    for action_id, endpoint in by_id.items():
        route = endpoint.matches[0]
        assert isinstance(route, RestRoute)  # the WeCom catalog is REST-only
        leaf = route.path.rstrip("/").rsplit("/", 1)[-1]
        policy = endpoint.default_policy
        if action_id == WeComAction.AUTH_BOOTSTRAP:
            assert policy == EndpointPolicy.DENY, action_id
        elif action_id == WeComAction.GATEWAY_FILE_UPLOAD:
            assert policy == EndpointPolicy.ASK, action_id
        elif action_id in (
            WeComAction.GATEWAY_DISCOVERY,
            WeComAction.GATEWAY_TASK_QUERY,
            WeComAction.GATEWAY_REMOTE_DOC,
        ):
            assert policy == EndpointPolicy.ALWAYS, action_id
        elif leaf in read_leaves:
            assert policy == EndpointPolicy.ALWAYS, action_id
        elif leaf in deny_leaves:
            assert policy == EndpointPolicy.DENY, action_id
        else:
            assert policy == EndpointPolicy.ASK, action_id
