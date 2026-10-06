"""The DingTalk provider catalog: every new-gen REST action the deployment's
permission points allow resolves to exactly one action, and default policies
follow the design (reads auto-approve; sends and creates/updates require
approval; deletes and the token endpoints are denied)."""

from __future__ import annotations

import pytest

from onyx.db.enums import EndpointPolicy, ExternalAppType
from onyx.external_apps.matching.request import MatchContext, ProxiedRequest
from onyx.external_apps.matching.rules import rule_matches
from onyx.external_apps.providers.actions import RestRoute
from onyx.external_apps.providers.dingtalk import DingTalkAction
from onyx.external_apps.providers.registry import get_endpoint_catalog

_CATALOG = get_endpoint_catalog(ExternalAppType.DINGTALK)


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
        # Token endpoints (the proxy mints tokens; never the agent).
        (
            "POST",
            "/v1.0/oauth2/accessToken",
            {DingTalkAction.AUTH_CORP_TOKEN},
        ),
        (
            "POST",
            "/v1.0/oauth2/userAccessToken",
            {DingTalkAction.AUTH_USER_TOKEN},
        ),
        # Knowledge base (wiki) — current v2 surface + doc-suite blocks.
        (
            "GET",
            "/v2.0/wiki/workspaces?operatorId=u1",
            {DingTalkAction.KB_LIST},
        ),
        (
            "GET",
            "/v2.0/wiki/nodes?operatorId=u1&parentNodeId=root",
            {DingTalkAction.KB_NODES_LIST},
        ),
        (
            "GET",
            "/v1.0/doc/suites/documents/doc123/blocks?operatorId=u1",
            {DingTalkAction.KB_NODE_CONTENT_GET},
        ),
        # Drive (钉盘).
        (
            "GET",
            "/v1.0/drive/spaces?unionId=u1",
            {DingTalkAction.DRIVE_SPACES_LIST},
        ),
        (
            "GET",
            "/v1.0/drive/spaces/s1/files?unionId=u1&parentId=0",
            {DingTalkAction.DRIVE_FILES_LIST},
        ),
        (
            "GET",
            "/v1.0/drive/spaces/s1/files/f1/downloadUrl?unionId=u1",
            {DingTalkAction.DRIVE_FILE_DOWNLOAD},
        ),
        # Todo.
        (
            "GET",
            "/v1.0/todo/users/u1/tasks",
            {DingTalkAction.TODO_TASKS_LIST},
        ),
        (
            "GET",
            "/v1.0/todo/users/u1/tasks/t1",
            {DingTalkAction.TODO_TASK_GET},
        ),
        (
            "POST",
            "/v1.0/todo/users/u1/tasks",
            {DingTalkAction.TODO_TASK_CREATE},
        ),
        (
            "PUT",
            "/v1.0/todo/users/u1/tasks/t1",
            {DingTalkAction.TODO_TASK_UPDATE},
        ),
        (
            "DELETE",
            "/v1.0/todo/users/u1/tasks/t1",
            {DingTalkAction.TODO_TASK_DELETE},
        ),
        # Calendar.
        (
            "GET",
            "/v1.0/calendar/users/u1/calendars/c1/events",
            {DingTalkAction.CALENDAR_EVENTS_LIST},
        ),
        (
            "GET",
            "/v1.0/calendar/users/u1/calendars/c1/events/e1",
            {DingTalkAction.CALENDAR_EVENT_GET},
        ),
        (
            "POST",
            "/v1.0/calendar/users/u1/calendars/c1/events",
            {DingTalkAction.CALENDAR_EVENT_CREATE},
        ),
        (
            "PUT",
            "/v1.0/calendar/users/u1/calendars/c1/events/e1",
            {DingTalkAction.CALENDAR_EVENT_UPDATE},
        ),
        (
            "DELETE",
            "/v1.0/calendar/users/u1/calendars/c1/events/e1",
            {DingTalkAction.CALENDAR_EVENT_DELETE},
        ),
        # Contacts.
        (
            "GET",
            "/v1.0/contact/users/u1",
            {DingTalkAction.CONTACT_USER_GET},
        ),
        (
            "POST",
            "/v1.0/contact/users/search",
            {DingTalkAction.CONTACT_USERS_SEARCH},
        ),
        # Robot sends and AI-card streaming.
        (
            "POST",
            "/v1.0/robot/oToMessages/batchSend",
            {DingTalkAction.ROBOT_O2O_SEND},
        ),
        (
            "POST",
            "/v1.0/robot/groupMessages/send",
            {DingTalkAction.ROBOT_GROUP_SEND},
        ),
        (
            "POST",
            "/v1.0/robot/messageFiles/download",
            {DingTalkAction.ROBOT_FILE_DOWNLOAD},
        ),
        (
            "POST",
            "/v1.0/card/instances",
            {DingTalkAction.CARD_INSTANCE_CREATE},
        ),
        (
            "POST",
            "/v1.0/card/instances/deliver",
            {DingTalkAction.CARD_INSTANCE_DELIVER},
        ),
        (
            "PUT",
            "/v1.0/card/streaming",
            {DingTalkAction.CARD_STREAMING_UPDATE},
        ),
    ],
)
def test_route_resolution(method: str, path: str, expected: set[str]) -> None:
    assert _matching_actions(method, path) == expected


def test_every_domain_is_represented() -> None:
    ids = {endpoint.id for endpoint in _CATALOG}
    for prefix in (
        "dingtalk.auth.",
        "dingtalk.kb.",
        "dingtalk.drive.",
        "dingtalk.todo.",
        "dingtalk.calendar.",
        "dingtalk.contact.",
        "dingtalk.robot.",
        "dingtalk.card.",
    ):
        assert any(id.startswith(prefix) for id in ids), prefix


def test_paths_are_unique_across_catalog() -> None:
    """One (method, path) per action: a request can never be attributed to
    two different governing policies."""
    seen: list[tuple[str, str]] = []
    for endpoint in _CATALOG:
        route = endpoint.matches[0]
        assert isinstance(route, RestRoute)  # the DingTalk catalog is REST-only
        seen.append((route.method, route.path))
    assert len(seen) == len(set(seen))


def test_default_policies_follow_convention() -> None:
    """Reads (incl. search and download-by-code, despite their POST verbs) are
    ALWAYS; sends and creates/updates are ASK; deletes and the token endpoints
    are DENY (the proxy mints tokens server-side, never the agent)."""
    always = {
        DingTalkAction.KB_LIST,
        DingTalkAction.KB_NODES_LIST,
        DingTalkAction.KB_NODE_CONTENT_GET,
        DingTalkAction.DRIVE_SPACES_LIST,
        DingTalkAction.DRIVE_FILES_LIST,
        DingTalkAction.DRIVE_FILE_DOWNLOAD,
        DingTalkAction.TODO_TASKS_LIST,
        DingTalkAction.TODO_TASK_GET,
        DingTalkAction.CALENDAR_EVENTS_LIST,
        DingTalkAction.CALENDAR_EVENT_GET,
        DingTalkAction.CONTACT_USER_GET,
        DingTalkAction.CONTACT_USERS_SEARCH,
        DingTalkAction.ROBOT_FILE_DOWNLOAD,
    }
    ask = {
        DingTalkAction.TODO_TASK_CREATE,
        DingTalkAction.TODO_TASK_UPDATE,
        DingTalkAction.CALENDAR_EVENT_CREATE,
        DingTalkAction.CALENDAR_EVENT_UPDATE,
        DingTalkAction.ROBOT_O2O_SEND,
        DingTalkAction.ROBOT_GROUP_SEND,
        DingTalkAction.CARD_INSTANCE_CREATE,
        DingTalkAction.CARD_INSTANCE_DELIVER,
        DingTalkAction.CARD_STREAMING_UPDATE,
    }
    deny = {
        DingTalkAction.AUTH_CORP_TOKEN,
        DingTalkAction.AUTH_USER_TOKEN,
        DingTalkAction.TODO_TASK_DELETE,
        DingTalkAction.CALENDAR_EVENT_DELETE,
    }
    by_id = {endpoint.id: endpoint for endpoint in _CATALOG}
    assert set(by_id) == always | ask | deny
    for action_id, endpoint in by_id.items():
        if action_id in always:
            assert endpoint.default_policy == EndpointPolicy.ALWAYS, action_id
        elif action_id in ask:
            assert endpoint.default_policy == EndpointPolicy.ASK, action_id
        else:
            assert endpoint.default_policy == EndpointPolicy.DENY, action_id


def test_unmatched_paths_have_no_action() -> None:
    """Anything off-catalog (e.g. the legacy kb surface) falls through to the
    whole-domain gate rule rather than matching a sibling action."""
    assert _matching_actions("GET", "/v1.0/kb/orgs/knowledgeBases") == set()
    assert _matching_actions("POST", "/v1.0/robot/emotion/reply") == set()
