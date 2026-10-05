"""The Feishu provider catalog: REST routes resolve to exactly the intended
action across every domain (IM, docs, wiki, drive, sheets, bitable, tasks,
calendar, contacts, approval, minutes, search), and default policies follow
the design (reads — including query-style POSTs — auto-approve; creates and
updates require approval; deletes are denied)."""

from __future__ import annotations

import pytest

from onyx.db.enums import EndpointPolicy, ExternalAppType
from onyx.error_handling.exceptions import OnyxError
from onyx.external_apps.matching.request import MatchContext, ProxiedRequest
from onyx.external_apps.matching.rules import rule_matches
from onyx.external_apps.providers.actions import RestRoute
from onyx.external_apps.providers.feishu import FeishuAction, FeishuProvider
from onyx.external_apps.providers.registry import get_endpoint_catalog

_CATALOG = get_endpoint_catalog(ExternalAppType.FEISHU)


def _matching_actions(method: str, path: str) -> set[str]:
    """Every catalog action whose rules recognise the request."""
    context = MatchContext(ProxiedRequest(method=method, path=path, body=None))
    return {
        endpoint.id
        for endpoint in _CATALOG
        if any(rule_matches(rule, context) for rule in endpoint.matches)
    }


@pytest.mark.parametrize(
    "method, path, expected",
    [
        # IM — method disambiguates the shared path, id segments bind loosely.
        ("POST", "/open-apis/im/v1/messages", {FeishuAction.MESSAGE_SEND}),
        ("GET", "/open-apis/im/v1/messages", {FeishuAction.MESSAGE_LIST}),
        ("GET", "/open-apis/im/v1/messages/om_1", {FeishuAction.MESSAGE_READ}),
        ("PATCH", "/open-apis/im/v1/messages/om_1", {FeishuAction.MESSAGE_UPDATE}),
        ("DELETE", "/open-apis/im/v1/messages/om_1", {FeishuAction.MESSAGE_DELETE}),
        (
            "POST",
            "/open-apis/im/v1/messages/om_1/reply",
            {FeishuAction.MESSAGE_REPLY},
        ),
        (
            "GET",
            "/open-apis/im/v1/messages/om_1/resources/img_key",
            {FeishuAction.MESSAGE_RESOURCE_GET},
        ),
        ("GET", "/open-apis/im/v1/chats", {FeishuAction.CHAT_LIST}),
        ("POST", "/open-apis/im/v1/chats", {FeishuAction.CHAT_CREATE}),
        ("GET", "/open-apis/im/v1/chats/oc_1", {FeishuAction.CHAT_GET}),
        (
            "GET",
            "/open-apis/im/v1/chats/oc_1/members",
            {FeishuAction.CHAT_MEMBERS},
        ),
        (
            "POST",
            "/open-apis/im/v1/chats/oc_1/members",
            {FeishuAction.CHAT_MEMBERS_ADD},
        ),
        # Docs.
        (
            "GET",
            "/open-apis/docx/v1/documents/DOC1/raw_content",
            {FeishuAction.DOC_READ},
        ),
        ("GET", "/open-apis/docx/v1/documents/DOC1", {FeishuAction.DOC_GET}),
        (
            "GET",
            "/open-apis/docx/v1/documents/DOC1/blocks",
            {FeishuAction.DOC_BLOCKS_LIST},
        ),
        (
            "POST",
            "/open-apis/docx/v1/documents/DOC1/blocks/BLK1/children",
            {FeishuAction.DOC_BLOCKS_CREATE},
        ),
        (
            "PATCH",
            "/open-apis/docx/v1/documents/DOC1/blocks/BLK1",
            {FeishuAction.DOC_BLOCKS_UPDATE},
        ),
        ("POST", "/open-apis/docx/v1/documents", {FeishuAction.DOC_CREATE}),
        (
            "POST",
            "/open-apis/suite/docs-api/search/object",
            {FeishuAction.DOCS_SEARCH},
        ),
        # Wiki.
        ("GET", "/open-apis/wiki/v2/spaces", {FeishuAction.WIKI_SPACES_LIST}),
        (
            "GET",
            "/open-apis/wiki/v2/spaces/741.../nodes",
            {FeishuAction.WIKI_NODES_LIST},
        ),
        (
            "GET",
            "/open-apis/wiki/v2/spaces/get_node",
            {FeishuAction.WIKI_NODE_GET},
        ),
        (
            "POST",
            "/open-apis/wiki/v2/spaces/741.../nodes",
            {FeishuAction.WIKI_NODE_CREATE},
        ),
        # Drive.
        (
            "GET",
            "/open-apis/drive/explorer/v2/root_folder/meta",
            {FeishuAction.DRIVE_ROOT_FOLDER_GET},
        ),
        ("GET", "/open-apis/drive/v1/files", {FeishuAction.DRIVE_FILES_LIST}),
        (
            "GET",
            "/open-apis/drive/v1/medias/CNabC/download",
            {FeishuAction.DRIVE_FILE_DOWNLOAD},
        ),
        (
            "POST",
            "/open-apis/drive/v1/medias/upload_all",
            {FeishuAction.DRIVE_FILE_UPLOAD},
        ),
        (
            "POST",
            "/open-apis/drive/v1/files/create_folder",
            {FeishuAction.DRIVE_FOLDER_CREATE},
        ),
        (
            "POST",
            "/open-apis/drive/v1/export_tasks",
            {FeishuAction.DRIVE_EXPORT_CREATE},
        ),
        (
            "GET",
            "/open-apis/drive/v1/export_tasks/ticket_1",
            {FeishuAction.DRIVE_EXPORT_GET},
        ),
        (
            "GET",
            "/open-apis/drive/v1/export_tasks/file/CNabC/download",
            {FeishuAction.DRIVE_EXPORT_DOWNLOAD},
        ),
        (
            "GET",
            "/open-apis/drive/v1/permissions/CNabC/members",
            {FeishuAction.DRIVE_PERMISSIONS_LIST},
        ),
        (
            "PATCH",
            "/open-apis/drive/v1/permissions/CNabC/public",
            {FeishuAction.DRIVE_PUBLIC_UPDATE},
        ),
        # Sheets.
        (
            "GET",
            "/open-apis/sheets/v3/spreadsheets/CNabC",
            {FeishuAction.SHEET_SPREADSHEET_GET},
        ),
        (
            "GET",
            "/open-apis/sheets/v2/spreadsheets/CNabC/metainfo",
            {FeishuAction.SHEET_METAINFO},
        ),
        (
            "GET",
            "/open-apis/sheets/v2/spreadsheets/CNabC/values/741!A1:D10",
            {FeishuAction.SHEET_VALUES_READ},
        ),
        (
            "PUT",
            "/open-apis/sheets/v2/spreadsheets/CNabC/values",
            {FeishuAction.SHEET_VALUES_WRITE},
        ),
        (
            "POST",
            "/open-apis/sheets/v2/spreadsheets/CNabC/values_prepend",
            {FeishuAction.SHEET_VALUES_PREPEND},
        ),
        # Bitable.
        (
            "GET",
            "/open-apis/bitable/v1/apps/CNabC/tables",
            {FeishuAction.BITABLE_TABLES_LIST},
        ),
        (
            "POST",
            "/open-apis/bitable/v1/apps/CNabC/tables",
            {FeishuAction.BITABLE_TABLE_CREATE},
        ),
        (
            "GET",
            "/open-apis/bitable/v1/apps/CNabC/tables/tbl1/fields",
            {FeishuAction.BITABLE_FIELDS_LIST},
        ),
        (
            "GET",
            "/open-apis/bitable/v1/apps/CNabC/tables/tbl1/records",
            {FeishuAction.BITABLE_RECORDS_LIST},
        ),
        (
            "POST",
            "/open-apis/bitable/v1/apps/CNabC/tables/tbl1/records/search",
            {FeishuAction.BITABLE_RECORDS_SEARCH},
        ),
        (
            "POST",
            "/open-apis/bitable/v1/apps/CNabC/tables/tbl1/records",
            {FeishuAction.BITABLE_RECORD_CREATE},
        ),
        (
            "PUT",
            "/open-apis/bitable/v1/apps/CNabC/tables/tbl1/records/rec1",
            {FeishuAction.BITABLE_RECORD_UPDATE},
        ),
        (
            "DELETE",
            "/open-apis/bitable/v1/apps/CNabC/tables/tbl1/records/rec1",
            {FeishuAction.BITABLE_RECORD_DELETE},
        ),
        # Tasks.
        ("GET", "/open-apis/task/v2/tasklists", {FeishuAction.TASKLISTS_LIST}),
        ("POST", "/open-apis/task/v2/tasklists", {FeishuAction.TASKLIST_CREATE}),
        (
            "GET",
            "/open-apis/task/v2/tasklists/tl1/tasks",
            {FeishuAction.TASKS_LIST},
        ),
        ("POST", "/open-apis/task/v2/tasks", {FeishuAction.TASK_CREATE}),
        ("GET", "/open-apis/task/v2/tasks/t_1", {FeishuAction.TASK_GET}),
        ("PATCH", "/open-apis/task/v2/tasks/t_1", {FeishuAction.TASK_UPDATE}),
        ("DELETE", "/open-apis/task/v2/tasks/t_1", {FeishuAction.TASK_DELETE}),
        (
            "GET",
            "/open-apis/task/v2/tasks/t_1/comments",
            {FeishuAction.TASK_COMMENTS_LIST},
        ),
        (
            "POST",
            "/open-apis/task/v2/tasks/t_1/comments",
            {FeishuAction.TASK_COMMENT_CREATE},
        ),
        # Calendar.
        ("GET", "/open-apis/calendar/v4/calendars", {FeishuAction.CALENDARS_LIST}),
        (
            "GET",
            "/open-apis/calendar/v4/calendars/cal_1",
            {FeishuAction.CALENDAR_GET},
        ),
        (
            "GET",
            "/open-apis/calendar/v4/calendars/cal_1/events",
            {FeishuAction.CALENDAR_EVENTS_LIST},
        ),
        (
            "GET",
            "/open-apis/calendar/v4/calendars/cal_1/events/ev_1",
            {FeishuAction.CALENDAR_EVENT_GET},
        ),
        (
            "POST",
            "/open-apis/calendar/v4/calendars/cal_1/events",
            {FeishuAction.CALENDAR_EVENT_CREATE},
        ),
        (
            "PATCH",
            "/open-apis/calendar/v4/calendars/cal_1/events/ev_1",
            {FeishuAction.CALENDAR_EVENT_UPDATE},
        ),
        (
            "DELETE",
            "/open-apis/calendar/v4/calendars/cal_1/events/ev_1",
            {FeishuAction.CALENDAR_EVENT_DELETE},
        ),
        (
            "POST",
            "/open-apis/calendar/v4/freebusy/query",
            {FeishuAction.CALENDAR_FREEBUSY_QUERY},
        ),
        # Contacts.
        (
            "GET",
            "/open-apis/contact/v3/users/ou_1",
            {FeishuAction.CONTACT_USER_GET},
        ),
        (
            "GET",
            "/open-apis/contact/v3/departments/0",
            {FeishuAction.CONTACT_DEPARTMENT_GET},
        ),
        (
            "GET",
            "/open-apis/contact/v3/departments/0/children",
            {FeishuAction.CONTACT_DEPARTMENTS_CHILDREN},
        ),
        (
            "POST",
            "/open-apis/contact/v3/users/batch_get_id",
            {FeishuAction.CONTACT_USERS_RESOLVE_IDS},
        ),
        # Approval.
        (
            "GET",
            "/open-apis/approval/v4/approvals",
            {FeishuAction.APPROVAL_DEFINITIONS_LIST},
        ),
        (
            "GET",
            "/open-apis/approval/v4/approvals/APPROVAL1",
            {FeishuAction.APPROVAL_DEFINITION_GET},
        ),
        (
            "POST",
            "/open-apis/approval/v4/instances",
            {FeishuAction.APPROVAL_INSTANCE_CREATE},
        ),
        (
            "GET",
            "/open-apis/approval/v4/instances/inst_1",
            {FeishuAction.APPROVAL_INSTANCE_GET},
        ),
        (
            "GET",
            "/open-apis/approval/v4/instances/inst_1/tasks",
            {FeishuAction.APPROVAL_INSTANCE_TASKS},
        ),
        # Minutes + search.
        ("GET", "/open-apis/minutes/v1/minutes", {FeishuAction.MINUTES_LIST}),
        (
            "GET",
            "/open-apis/minutes/v1/minutes/CNabC/transcript",
            {FeishuAction.MINUTES_TRANSCRIPT_GET},
        ),
        (
            "POST",
            "/open-apis/search/v2/message",
            {FeishuAction.MESSAGE_SEARCH},
        ),
        # Mail. POST /send disambiguates from the {message_id} read route.
        (
            "GET",
            "/open-apis/mail/v1/user_mailboxes/me",
            {FeishuAction.MAILBOX_GET},
        ),
        (
            "GET",
            "/open-apis/mail/v1/user_mailboxes/me/messages",
            {FeishuAction.MAIL_MESSAGES_LIST},
        ),
        (
            "GET",
            "/open-apis/mail/v1/user_mailboxes/me/messages/m_1",
            {FeishuAction.MAIL_MESSAGE_GET},
        ),
        (
            "POST",
            "/open-apis/mail/v1/user_mailboxes/me/messages/send",
            {FeishuAction.MAIL_SEND},
        ),
        (
            "POST",
            "/open-apis/mail/v1/user_mailboxes/me/drafts",
            {FeishuAction.MAIL_DRAFT_CREATE},
        ),
        (
            "PUT",
            "/open-apis/mail/v1/user_mailboxes/me/drafts/d_1",
            {FeishuAction.MAIL_DRAFT_UPDATE},
        ),
        (
            "POST",
            "/open-apis/mail/v1/user_mailboxes/me/drafts/d_1/send",
            {FeishuAction.MAIL_DRAFT_SEND},
        ),
        (
            "GET",
            "/open-apis/mail/v1/user_mailboxes/me/folders",
            {FeishuAction.MAIL_FOLDERS_LIST},
        ),
        (
            "GET",
            "/open-apis/mail/v1/user_mailboxes/me/labels",
            {FeishuAction.MAIL_LABELS_LIST},
        ),
        # VC.
        ("GET", "/open-apis/vc/v1/meetings", {FeishuAction.VC_MEETINGS_LIST}),
        (
            "GET",
            "/open-apis/vc/v1/meetings/mtg_1",
            {FeishuAction.VC_MEETING_GET},
        ),
        (
            "GET",
            "/open-apis/vc/v1/meetings/mtg_1/participants",
            {FeishuAction.VC_PARTICIPANTS_LIST},
        ),
        (
            "GET",
            "/open-apis/vc/v1/meetings/mtg_1/reports",
            {FeishuAction.VC_MEETING_REPORTS},
        ),
        ("POST", "/open-apis/vc/v1/reserves", {FeishuAction.VC_RESERVE_CREATE}),
        (
            "GET",
            "/open-apis/vc/v1/reserves/rsv_1",
            {FeishuAction.VC_RESERVE_GET},
        ),
        (
            "DELETE",
            "/open-apis/vc/v1/reserves/rsv_1",
            {FeishuAction.VC_RESERVE_DELETE},
        ),
        # OKR.
        ("GET", "/open-apis/okr/v1/periods", {FeishuAction.OKR_PERIODS_LIST}),
        (
            "GET",
            "/open-apis/okr/v1/periods/p_1",
            {FeishuAction.OKR_PERIOD_GET},
        ),
        (
            "GET",
            "/open-apis/okr/v1/users/ou_1/user_okrs",
            {FeishuAction.OKR_USER_OKRS},
        ),
        # Whiteboard.
        (
            "GET",
            "/open-apis/board/v1/whiteboards/bd_1/nodes",
            {FeishuAction.BOARD_NODES_LIST},
        ),
        (
            "POST",
            "/open-apis/board/v1/whiteboards",
            {FeishuAction.BOARD_CREATE},
        ),
        # Attendance (sensitive — ASK by default).
        (
            "POST",
            "/open-apis/attendance/v1/user_tasks/query",
            {FeishuAction.ATTENDANCE_TASKS_QUERY},
        ),
        # Drive comments.
        (
            "GET",
            "/open-apis/drive/v1/files/CNabC/comments",
            {FeishuAction.DRIVE_COMMENTS_LIST},
        ),
        (
            "POST",
            "/open-apis/drive/v1/files/CNabC/comments",
            {FeishuAction.DRIVE_COMMENT_CREATE},
        ),
    ],
)
def test_route_resolves_to_expected_action(
    method: str, path: str, expected: set[str]
) -> None:
    assert _matching_actions(method, path) == expected


def test_find_by_department_overlaps_user_get() -> None:
    """Feishu's own API collides here: /contact/v3/users/find_by_department
    also matches /contact/v3/users/{user_id}. Both default to ALWAYS, so the
    strictest-policy-wins gate is unaffected."""
    matched = _matching_actions("GET", "/open-apis/contact/v3/users/find_by_department")
    assert {
        FeishuAction.CONTACT_USERS_BY_DEPARTMENT,
        FeishuAction.CONTACT_USER_GET,
    } == matched


def test_every_domain_is_represented() -> None:
    ids = {endpoint.id for endpoint in _CATALOG}
    for prefix in (
        "feishu.message.",
        "feishu.chat.",
        "feishu.doc.",
        "feishu.wiki.",
        "feishu.drive.",
        "feishu.sheet.",
        "feishu.bitable.",
        "feishu.task.",
        "feishu.calendar.",
        "feishu.contact.",
        "feishu.approval.",
        "feishu.minutes.",
        "feishu.search.",
        "feishu.mail.",
        "feishu.vc.",
        "feishu.okr.",
        "feishu.board.",
        "feishu.attendance.",
    ):
        assert any(id.startswith(prefix) for id in ids), prefix


def test_default_policies_follow_convention() -> None:
    """GETs are reads (ALWAYS), DELETEs are DENY, and every other write is
    ASK — except the explicitly read-shaped POST queries listed here. The
    attendance query POST is intentionally NOT exempt: check-in records are
    sensitive personal data, so it stays behind ASK approval."""
    read_posts = {
        FeishuAction.DOCS_SEARCH,
        FeishuAction.BITABLE_RECORDS_SEARCH,
        FeishuAction.CALENDAR_FREEBUSY_QUERY,
        FeishuAction.CONTACT_USERS_RESOLVE_IDS,
        FeishuAction.MESSAGE_SEARCH,
    }
    by_id = {endpoint.id: endpoint for endpoint in _CATALOG}
    for action_id, endpoint in by_id.items():
        route = endpoint.matches[0]
        assert isinstance(route, RestRoute)  # the Feishu catalog is REST-only
        policy = endpoint.default_policy
        if route.method == "GET":
            assert policy == EndpointPolicy.ALWAYS, action_id
        elif route.method == "DELETE":
            assert policy == EndpointPolicy.DENY, action_id
        elif route.method == "POST" and action_id in read_posts:
            assert policy == EndpointPolicy.ALWAYS, action_id
        else:
            assert policy == EndpointPolicy.ASK, action_id


def test_extract_credentials_maps_standard_fields() -> None:
    creds = FeishuProvider().extract_credentials(
        {
            "access_token": "u-xxxx",
            "token_type": "Bearer",
            "refresh_token": "ur-xxxx",
            "expires_in": 6900,
        }
    )
    assert creds == {
        "access_token": "u-xxxx",
        "token_type": "Bearer",
        "refresh_token": "ur-xxxx",
        "expires_in": 6900,
    }


def test_extract_credentials_requires_access_token() -> None:
    with pytest.raises(OnyxError):
        FeishuProvider().extract_credentials({"code": 20029, "msg": "bad code"})
