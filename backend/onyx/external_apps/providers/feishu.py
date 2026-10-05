from typing import Any

from onyx.db.enums import EndpointPolicy, ExternalAppType
from onyx.error_handling.error_codes import OnyxErrorCode
from onyx.error_handling.exceptions import OnyxError
from onyx.external_apps.providers.actions import (
    EndpointSpec,
    ExternalAppAction,
    RestRoute,
)
from onyx.external_apps.providers.base import (
    AdminDescriptorSpec,
    OAuthExternalAppProvider,
    OAuthFlowSpec,
    OAuthProviderSpec,
    OrgCredentialField,
)

FEISHU_SETUP_PERMISSIONS = """\
im:message (发消息)、im:message:readonly (读消息/历史)、im:message.p2p_msg:readonly 与 \
im:message.group_at_msg:readonly (接收事件，机器人场景)、im:chat 与 im:chat:readonly (群信息/建群)、\
im:resource (消息图片/文件下载，若无此项则跳过)、docx:document 与 docx:document:readonly (文档读写)、\
wiki:wiki 与 wiki:wiki:readonly (知识库)、drive:drive 与 drive:drive:readonly (云盘读写)、\
sheets:spreadsheet 与 sheets:spreadsheet:readonly (电子表格)、bitable:app 与 bitable:app:readonly \
(多维表格)、task:task 与 task:task:readonly (任务)、calendar:calendar 与 calendar:calendar:readonly \
(日历)、contact:user.base:readonly 与 contact:contact.base:readonly (通讯录)。\
搜索、审批、妙记等域的权限按需在权限管理页搜索开启；全部勾选后必须在「版本管理与发布」\
创建并发布新版本才生效。"""


class FeishuAction(ExternalAppAction):
    """Strongly-typed catalog ids for the Feishu provider."""

    # --- IM: messages ---
    MESSAGE_SEND = "feishu.message.send"
    MESSAGE_READ = "feishu.message.read"
    MESSAGE_LIST = "feishu.message.list"
    MESSAGE_REPLY = "feishu.message.reply"
    MESSAGE_UPDATE = "feishu.message.update"
    MESSAGE_DELETE = "feishu.message.delete"
    MESSAGE_RESOURCE_GET = "feishu.message.resource.get"
    # --- IM: chats ---
    CHAT_LIST = "feishu.chat.list"
    CHAT_GET = "feishu.chat.get"
    CHAT_MEMBERS = "feishu.chat.members"
    CHAT_CREATE = "feishu.chat.create"
    CHAT_MEMBERS_ADD = "feishu.chat.members.add"
    # --- Docs (docx) ---
    DOC_READ = "feishu.doc.read"
    DOC_GET = "feishu.doc.get"
    DOC_BLOCKS_LIST = "feishu.doc.blocks.list"
    DOC_BLOCKS_CREATE = "feishu.doc.blocks.create"
    DOC_BLOCKS_UPDATE = "feishu.doc.blocks.update"
    DOC_CREATE = "feishu.doc.create"
    DOCS_SEARCH = "feishu.docs.search"
    # --- Wiki ---
    WIKI_SPACES_LIST = "feishu.wiki.spaces.list"
    WIKI_NODES_LIST = "feishu.wiki.nodes.list"
    WIKI_NODE_GET = "feishu.wiki.node.get"
    WIKI_NODE_CREATE = "feishu.wiki.node.create"
    # --- Drive ---
    DRIVE_ROOT_FOLDER_GET = "feishu.drive.root_folder.get"
    DRIVE_FILES_LIST = "feishu.drive.files.list"
    DRIVE_FILE_DOWNLOAD = "feishu.drive.file.download"
    DRIVE_FILE_UPLOAD = "feishu.drive.file.upload"
    DRIVE_FOLDER_CREATE = "feishu.drive.folder.create"
    DRIVE_EXPORT_CREATE = "feishu.drive.export.create"
    DRIVE_EXPORT_GET = "feishu.drive.export.get"
    DRIVE_EXPORT_DOWNLOAD = "feishu.drive.export.download"
    DRIVE_PERMISSIONS_LIST = "feishu.drive.permissions.list"
    DRIVE_PUBLIC_UPDATE = "feishu.drive.public.update"
    # --- Sheets ---
    SHEET_SPREADSHEET_GET = "feishu.sheet.spreadsheet.get"
    SHEET_METAINFO = "feishu.sheet.metainfo"
    SHEET_VALUES_READ = "feishu.sheet.values.read"
    SHEET_VALUES_WRITE = "feishu.sheet.values.write"
    SHEET_VALUES_PREPEND = "feishu.sheet.values.prepend"
    # --- Bitable ---
    BITABLE_TABLES_LIST = "feishu.bitable.tables.list"
    BITABLE_TABLE_CREATE = "feishu.bitable.table.create"
    BITABLE_FIELDS_LIST = "feishu.bitable.fields.list"
    BITABLE_RECORDS_LIST = "feishu.bitable.records.list"
    BITABLE_RECORDS_SEARCH = "feishu.bitable.records.search"
    BITABLE_RECORD_CREATE = "feishu.bitable.record.create"
    BITABLE_RECORD_UPDATE = "feishu.bitable.record.update"
    BITABLE_RECORD_DELETE = "feishu.bitable.record.delete"
    # --- Tasks ---
    TASKLISTS_LIST = "feishu.task.tasklists.list"
    TASKLIST_CREATE = "feishu.task.tasklist.create"
    TASKS_LIST = "feishu.task.tasks.list"
    TASK_CREATE = "feishu.task.create"
    TASK_GET = "feishu.task.get"
    TASK_UPDATE = "feishu.task.update"
    TASK_DELETE = "feishu.task.delete"
    TASK_COMMENTS_LIST = "feishu.task.comments.list"
    TASK_COMMENT_CREATE = "feishu.task.comment.create"
    # --- Calendar ---
    CALENDARS_LIST = "feishu.calendar.calendars.list"
    CALENDAR_GET = "feishu.calendar.get"
    CALENDAR_EVENTS_LIST = "feishu.calendar.events.list"
    CALENDAR_EVENT_GET = "feishu.calendar.event.get"
    CALENDAR_EVENT_CREATE = "feishu.calendar.event.create"
    CALENDAR_EVENT_UPDATE = "feishu.calendar.event.update"
    CALENDAR_EVENT_DELETE = "feishu.calendar.event.delete"
    CALENDAR_FREEBUSY_QUERY = "feishu.calendar.freebusy.query"
    # --- Contacts ---
    CONTACT_USER_GET = "feishu.contact.user.get"
    CONTACT_USERS_BY_DEPARTMENT = "feishu.contact.users.by_department"
    CONTACT_DEPARTMENT_GET = "feishu.contact.department.get"
    CONTACT_DEPARTMENTS_CHILDREN = "feishu.contact.departments.children"
    CONTACT_USERS_RESOLVE_IDS = "feishu.contact.users.resolve_ids"
    # --- Approval ---
    APPROVAL_DEFINITIONS_LIST = "feishu.approval.definitions.list"
    APPROVAL_DEFINITION_GET = "feishu.approval.definition.get"
    APPROVAL_INSTANCE_CREATE = "feishu.approval.instance.create"
    APPROVAL_INSTANCE_GET = "feishu.approval.instance.get"
    APPROVAL_INSTANCE_TASKS = "feishu.approval.instance.tasks"
    # --- Minutes ---
    MINUTES_LIST = "feishu.minutes.list"
    MINUTES_TRANSCRIPT_GET = "feishu.minutes.transcript.get"
    # --- Search ---
    MESSAGE_SEARCH = "feishu.search.message"


# open.feishu.cn REST surface; every action rides with the user_access_token
# obtained through passport.feishu.cn (see OAuthFlowSpec). Reads default to
# ALWAYS, creates/sends/updates to ASK, deletes to DENY — admins can override
# each individually. Query strings are stripped before matching, so options
# like receive_id_type never affect routing.
_ENDPOINTS: list[EndpointSpec] = [
    # ============================== IM ==============================
    EndpointSpec(
        id=FeishuAction.MESSAGE_SEND,
        normalised_name="Send a message",
        description="Send a text/post/image/interactive message to a user or chat.",
        matches=(RestRoute(method="POST", path="/open-apis/im/v1/messages"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=FeishuAction.MESSAGE_READ,
        normalised_name="Read a message",
        description="Fetch a single message by id.",
        matches=(
            RestRoute(method="GET", path="/open-apis/im/v1/messages/{message_id}"),
        ),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=FeishuAction.MESSAGE_LIST,
        normalised_name="List chat history",
        description="List a chat's historical messages in a time window.",
        matches=(RestRoute(method="GET", path="/open-apis/im/v1/messages"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=FeishuAction.MESSAGE_REPLY,
        normalised_name="Reply to a message",
        description="Reply inside a message's thread.",
        matches=(
            RestRoute(
                method="POST", path="/open-apis/im/v1/messages/{message_id}/reply"
            ),
        ),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=FeishuAction.MESSAGE_UPDATE,
        normalised_name="Update a message card",
        description="Update an interactive card message in place.",
        matches=(
            RestRoute(method="PATCH", path="/open-apis/im/v1/messages/{message_id}"),
        ),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=FeishuAction.MESSAGE_DELETE,
        normalised_name="Delete a message",
        description="Recall/delete a sent message.",
        matches=(
            RestRoute(method="DELETE", path="/open-apis/im/v1/messages/{message_id}"),
        ),
        default_policy=EndpointPolicy.DENY,
    ),
    EndpointSpec(
        id=FeishuAction.MESSAGE_RESOURCE_GET,
        normalised_name="Download a message resource",
        description="Download an image or file attached to a message.",
        matches=(
            RestRoute(
                method="GET",
                path="/open-apis/im/v1/messages/{message_id}/resources/{file_key}",
            ),
        ),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    # ============================== IM: chats ==============================
    EndpointSpec(
        id=FeishuAction.CHAT_LIST,
        normalised_name="List chats",
        description="List the group chats the user is in.",
        matches=(RestRoute(method="GET", path="/open-apis/im/v1/chats"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=FeishuAction.CHAT_GET,
        normalised_name="Get chat info",
        description="Fetch a group chat's metadata.",
        matches=(RestRoute(method="GET", path="/open-apis/im/v1/chats/{chat_id}"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=FeishuAction.CHAT_MEMBERS,
        normalised_name="List chat members",
        description="List the members of a group chat.",
        matches=(
            RestRoute(method="GET", path="/open-apis/im/v1/chats/{chat_id}/members"),
        ),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=FeishuAction.CHAT_CREATE,
        normalised_name="Create a group chat",
        description="Create a new group chat.",
        matches=(RestRoute(method="POST", path="/open-apis/im/v1/chats"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=FeishuAction.CHAT_MEMBERS_ADD,
        normalised_name="Add chat members",
        description="Add members to a group chat.",
        matches=(
            RestRoute(method="POST", path="/open-apis/im/v1/chats/{chat_id}/members"),
        ),
        default_policy=EndpointPolicy.ASK,
    ),
    # ============================== Docs (docx) ==============================
    EndpointSpec(
        id=FeishuAction.DOC_READ,
        normalised_name="Read a document",
        description="Read a docx document's plain-text content.",
        matches=(
            RestRoute(
                method="GET",
                path="/open-apis/docx/v1/documents/{document_id}/raw_content",
            ),
        ),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=FeishuAction.DOC_GET,
        normalised_name="Get document metadata",
        description="Fetch a document's title and metadata.",
        matches=(
            RestRoute(method="GET", path="/open-apis/docx/v1/documents/{document_id}"),
        ),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=FeishuAction.DOC_BLOCKS_LIST,
        normalised_name="List document blocks",
        description="List the structured blocks (paragraphs, tables, ...) of a document.",
        matches=(
            RestRoute(
                method="GET",
                path="/open-apis/docx/v1/documents/{document_id}/blocks",
            ),
        ),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=FeishuAction.DOC_BLOCKS_CREATE,
        normalised_name="Add blocks to a document",
        description="Append or insert content blocks into a document.",
        matches=(
            RestRoute(
                method="POST",
                path="/open-apis/docx/v1/documents/{document_id}/blocks/{block_id}/children",
            ),
        ),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=FeishuAction.DOC_BLOCKS_UPDATE,
        normalised_name="Update a document block",
        description="Update the content of a single block.",
        matches=(
            RestRoute(
                method="PATCH",
                path="/open-apis/docx/v1/documents/{document_id}/blocks/{block_id}",
            ),
        ),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=FeishuAction.DOC_CREATE,
        normalised_name="Create a document",
        description="Create a new docx document (optionally inside a folder).",
        matches=(RestRoute(method="POST", path="/open-apis/docx/v1/documents"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=FeishuAction.DOCS_SEARCH,
        normalised_name="Search documents",
        description="Search the workspace's cloud documents by keyword.",
        matches=(
            RestRoute(method="POST", path="/open-apis/suite/docs-api/search/object"),
        ),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    # ============================== Wiki ==============================
    EndpointSpec(
        id=FeishuAction.WIKI_SPACES_LIST,
        normalised_name="List wiki spaces",
        description="List the knowledge spaces visible to the user.",
        matches=(RestRoute(method="GET", path="/open-apis/wiki/v2/spaces"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=FeishuAction.WIKI_NODES_LIST,
        normalised_name="List wiki nodes",
        description="List a knowledge space's node tree (pages, docs, sheets).",
        matches=(
            RestRoute(method="GET", path="/open-apis/wiki/v2/spaces/{space_id}/nodes"),
        ),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=FeishuAction.WIKI_NODE_GET,
        normalised_name="Get a wiki node",
        description="Resolve a wiki node (and its actual document token) by token.",
        matches=(RestRoute(method="GET", path="/open-apis/wiki/v2/spaces/get_node"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=FeishuAction.WIKI_NODE_CREATE,
        normalised_name="Create a wiki node",
        description="Create a page/document under a knowledge space.",
        matches=(
            RestRoute(method="POST", path="/open-apis/wiki/v2/spaces/{space_id}/nodes"),
        ),
        default_policy=EndpointPolicy.ASK,
    ),
    # ============================== Drive ==============================
    EndpointSpec(
        id=FeishuAction.DRIVE_ROOT_FOLDER_GET,
        normalised_name="Get root folder",
        description="Fetch the user's drive root folder metadata.",
        matches=(
            RestRoute(
                method="GET", path="/open-apis/drive/explorer/v2/root_folder/meta"
            ),
        ),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=FeishuAction.DRIVE_FILES_LIST,
        normalised_name="List drive files",
        description="List files/folders inside a drive folder.",
        matches=(RestRoute(method="GET", path="/open-apis/drive/v1/files"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=FeishuAction.DRIVE_FILE_DOWNLOAD,
        normalised_name="Download a drive file",
        description="Download an uploaded file's content by token.",
        matches=(
            RestRoute(
                method="GET",
                path="/open-apis/drive/v1/medias/{file_token}/download",
            ),
        ),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=FeishuAction.DRIVE_FILE_UPLOAD,
        normalised_name="Upload a file",
        description="Upload a file to the user's drive.",
        matches=(
            RestRoute(method="POST", path="/open-apis/drive/v1/medias/upload_all"),
        ),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=FeishuAction.DRIVE_FOLDER_CREATE,
        normalised_name="Create a folder",
        description="Create a folder in the drive.",
        matches=(
            RestRoute(method="POST", path="/open-apis/drive/v1/files/create_folder"),
        ),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=FeishuAction.DRIVE_EXPORT_CREATE,
        normalised_name="Create an export task",
        description="Export a doc/sheet/bitable to a file (e.g. CSV/PDF) via an export task.",
        matches=(RestRoute(method="POST", path="/open-apis/drive/v1/export_tasks"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=FeishuAction.DRIVE_EXPORT_GET,
        normalised_name="Check an export task",
        description="Poll an export task's status by ticket.",
        matches=(
            RestRoute(method="GET", path="/open-apis/drive/v1/export_tasks/{ticket}"),
        ),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=FeishuAction.DRIVE_EXPORT_DOWNLOAD,
        normalised_name="Download an exported file",
        description="Download the file produced by an export task.",
        matches=(
            RestRoute(
                method="GET",
                path="/open-apis/drive/v1/export_tasks/file/{file_token}/download",
            ),
        ),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=FeishuAction.DRIVE_PERMISSIONS_LIST,
        normalised_name="List permission members",
        description="List who can access a drive/wiki document.",
        matches=(
            RestRoute(
                method="GET",
                path="/open-apis/drive/v1/permissions/{token}/members",
            ),
        ),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=FeishuAction.DRIVE_PUBLIC_UPDATE,
        normalised_name="Update sharing settings",
        description="Change a document's public/sharing settings.",
        matches=(
            RestRoute(
                method="PATCH",
                path="/open-apis/drive/v1/permissions/{token}/public",
            ),
        ),
        default_policy=EndpointPolicy.ASK,
    ),
    # ============================== Sheets ==============================
    EndpointSpec(
        id=FeishuAction.SHEET_SPREADSHEET_GET,
        normalised_name="Get spreadsheet metadata",
        description="Fetch a spreadsheet's sheets and metadata.",
        matches=(
            RestRoute(
                method="GET",
                path="/open-apis/sheets/v3/spreadsheets/{spreadsheet_token}",
            ),
        ),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=FeishuAction.SHEET_METAINFO,
        normalised_name="Get sheet dimensions",
        description="Fetch rows/columns counts for the sheets in a spreadsheet.",
        matches=(
            RestRoute(
                method="GET",
                path="/open-apis/sheets/v2/spreadsheets/{spreadsheet_token}/metainfo",
            ),
        ),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=FeishuAction.SHEET_VALUES_READ,
        normalised_name="Read sheet values",
        description="Read a cell range's values from a spreadsheet.",
        matches=(
            RestRoute(
                method="GET",
                path="/open-apis/sheets/v2/spreadsheets/{spreadsheet_token}/values/{range}",
            ),
        ),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=FeishuAction.SHEET_VALUES_WRITE,
        normalised_name="Write sheet values",
        description="Write values into a cell range of a spreadsheet.",
        matches=(
            RestRoute(
                method="PUT",
                path="/open-apis/sheets/v2/spreadsheets/{spreadsheet_token}/values",
            ),
        ),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=FeishuAction.SHEET_VALUES_PREPEND,
        normalised_name="Prepend sheet values",
        description="Insert values above an existing row range.",
        matches=(
            RestRoute(
                method="POST",
                path="/open-apis/sheets/v2/spreadsheets/{spreadsheet_token}/values_prepend",
            ),
        ),
        default_policy=EndpointPolicy.ASK,
    ),
    # ============================== Bitable ==============================
    EndpointSpec(
        id=FeishuAction.BITABLE_TABLES_LIST,
        normalised_name="List bitable tables",
        description="List the data tables inside a multi-dimensional table app.",
        matches=(
            RestRoute(
                method="GET",
                path="/open-apis/bitable/v1/apps/{app_token}/tables",
            ),
        ),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=FeishuAction.BITABLE_TABLE_CREATE,
        normalised_name="Create a bitable table",
        description="Create a data table inside a multi-dimensional table app.",
        matches=(
            RestRoute(
                method="POST",
                path="/open-apis/bitable/v1/apps/{app_token}/tables",
            ),
        ),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=FeishuAction.BITABLE_FIELDS_LIST,
        normalised_name="List bitable fields",
        description="List a data table's field definitions.",
        matches=(
            RestRoute(
                method="GET",
                path="/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields",
            ),
        ),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=FeishuAction.BITABLE_RECORDS_LIST,
        normalised_name="List bitable records",
        description="List the records of a data table.",
        matches=(
            RestRoute(
                method="GET",
                path="/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records",
            ),
        ),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=FeishuAction.BITABLE_RECORDS_SEARCH,
        normalised_name="Search bitable records",
        description="Search/filter records in a data table.",
        matches=(
            RestRoute(
                method="POST",
                path="/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/search",
            ),
        ),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=FeishuAction.BITABLE_RECORD_CREATE,
        normalised_name="Create a bitable record",
        description="Add a record to a data table.",
        matches=(
            RestRoute(
                method="POST",
                path="/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records",
            ),
        ),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=FeishuAction.BITABLE_RECORD_UPDATE,
        normalised_name="Update a bitable record",
        description="Update a record's field values.",
        matches=(
            RestRoute(
                method="PUT",
                path="/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}",
            ),
        ),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=FeishuAction.BITABLE_RECORD_DELETE,
        normalised_name="Delete a bitable record",
        description="Delete a record from a data table.",
        matches=(
            RestRoute(
                method="DELETE",
                path="/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}",
            ),
        ),
        default_policy=EndpointPolicy.DENY,
    ),
    # ============================== Tasks ==============================
    EndpointSpec(
        id=FeishuAction.TASKLISTS_LIST,
        normalised_name="List task lists",
        description="List the user's task lists.",
        matches=(RestRoute(method="GET", path="/open-apis/task/v2/tasklists"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=FeishuAction.TASKLIST_CREATE,
        normalised_name="Create a task list",
        description="Create a new task list.",
        matches=(RestRoute(method="POST", path="/open-apis/task/v2/tasklists"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=FeishuAction.TASKS_LIST,
        normalised_name="List tasks",
        description="List the tasks inside a task list.",
        matches=(
            RestRoute(
                method="GET",
                path="/open-apis/task/v2/tasklists/{tasklist_guid}/tasks",
            ),
        ),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=FeishuAction.TASK_CREATE,
        normalised_name="Create a task",
        description="Create a task, optionally assigned to someone with a due date.",
        matches=(RestRoute(method="POST", path="/open-apis/task/v2/tasks"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=FeishuAction.TASK_GET,
        normalised_name="Get a task",
        description="Fetch a task's details.",
        matches=(RestRoute(method="GET", path="/open-apis/task/v2/tasks/{task_guid}"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=FeishuAction.TASK_UPDATE,
        normalised_name="Update a task",
        description="Update a task's fields, including completing it.",
        matches=(
            RestRoute(method="PATCH", path="/open-apis/task/v2/tasks/{task_guid}"),
        ),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=FeishuAction.TASK_DELETE,
        normalised_name="Delete a task",
        description="Delete a task.",
        matches=(
            RestRoute(method="DELETE", path="/open-apis/task/v2/tasks/{task_guid}"),
        ),
        default_policy=EndpointPolicy.DENY,
    ),
    EndpointSpec(
        id=FeishuAction.TASK_COMMENTS_LIST,
        normalised_name="List task comments",
        description="List the comments on a task.",
        matches=(
            RestRoute(
                method="GET",
                path="/open-apis/task/v2/tasks/{task_guid}/comments",
            ),
        ),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=FeishuAction.TASK_COMMENT_CREATE,
        normalised_name="Comment on a task",
        description="Add a comment to a task.",
        matches=(
            RestRoute(
                method="POST",
                path="/open-apis/task/v2/tasks/{task_guid}/comments",
            ),
        ),
        default_policy=EndpointPolicy.ASK,
    ),
    # ============================== Calendar ==============================
    EndpointSpec(
        id=FeishuAction.CALENDARS_LIST,
        normalised_name="List calendars",
        description="List the calendars in the user's calendar list.",
        matches=(RestRoute(method="GET", path="/open-apis/calendar/v4/calendars"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=FeishuAction.CALENDAR_GET,
        normalised_name="Get calendar info",
        description="Fetch a calendar's metadata.",
        matches=(
            RestRoute(
                method="GET", path="/open-apis/calendar/v4/calendars/{calendar_id}"
            ),
        ),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=FeishuAction.CALENDAR_EVENTS_LIST,
        normalised_name="List calendar events",
        description="List a calendar's events in a time window.",
        matches=(
            RestRoute(
                method="GET",
                path="/open-apis/calendar/v4/calendars/{calendar_id}/events",
            ),
        ),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=FeishuAction.CALENDAR_EVENT_GET,
        normalised_name="Get an event",
        description="Fetch a calendar event's details.",
        matches=(
            RestRoute(
                method="GET",
                path="/open-apis/calendar/v4/calendars/{calendar_id}/events/{event_id}",
            ),
        ),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=FeishuAction.CALENDAR_EVENT_CREATE,
        normalised_name="Create an event",
        description="Create an event on a calendar, optionally inviting attendees.",
        matches=(
            RestRoute(
                method="POST",
                path="/open-apis/calendar/v4/calendars/{calendar_id}/events",
            ),
        ),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=FeishuAction.CALENDAR_EVENT_UPDATE,
        normalised_name="Update an event",
        description="Update a calendar event.",
        matches=(
            RestRoute(
                method="PATCH",
                path="/open-apis/calendar/v4/calendars/{calendar_id}/events/{event_id}",
            ),
        ),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=FeishuAction.CALENDAR_EVENT_DELETE,
        normalised_name="Delete an event",
        description="Delete a calendar event.",
        matches=(
            RestRoute(
                method="DELETE",
                path="/open-apis/calendar/v4/calendars/{calendar_id}/events/{event_id}",
            ),
        ),
        default_policy=EndpointPolicy.DENY,
    ),
    EndpointSpec(
        id=FeishuAction.CALENDAR_FREEBUSY_QUERY,
        normalised_name="Query free/busy",
        description="Query users' free/busy time to find meeting slots.",
        matches=(
            RestRoute(method="POST", path="/open-apis/calendar/v4/freebusy/query"),
        ),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    # ============================== Contacts ==============================
    EndpointSpec(
        id=FeishuAction.CONTACT_USER_GET,
        normalised_name="Get a user",
        description="Fetch a colleague's profile (name, email, department).",
        matches=(
            RestRoute(method="GET", path="/open-apis/contact/v3/users/{user_id}"),
        ),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=FeishuAction.CONTACT_USERS_BY_DEPARTMENT,
        normalised_name="List department users",
        description="List the members of a department.",
        matches=(
            RestRoute(
                method="GET",
                path="/open-apis/contact/v3/users/find_by_department",
            ),
        ),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=FeishuAction.CONTACT_DEPARTMENT_GET,
        normalised_name="Get a department",
        description="Fetch a department's details.",
        matches=(
            RestRoute(
                method="GET",
                path="/open-apis/contact/v3/departments/{department_id}",
            ),
        ),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=FeishuAction.CONTACT_DEPARTMENTS_CHILDREN,
        normalised_name="List child departments",
        description="List a department's child departments.",
        matches=(
            RestRoute(
                method="GET",
                path="/open-apis/contact/v3/departments/{department_id}/children",
            ),
        ),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=FeishuAction.CONTACT_USERS_RESOLVE_IDS,
        normalised_name="Resolve users by email/phone",
        description="Map emails or phone numbers to Feishu user ids.",
        matches=(
            RestRoute(method="POST", path="/open-apis/contact/v3/users/batch_get_id"),
        ),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    # ============================== Approval ==============================
    EndpointSpec(
        id=FeishuAction.APPROVAL_DEFINITIONS_LIST,
        normalised_name="List approval definitions",
        description="List the approval definitions the app can access.",
        matches=(RestRoute(method="GET", path="/open-apis/approval/v4/approvals"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=FeishuAction.APPROVAL_DEFINITION_GET,
        normalised_name="Get an approval definition",
        description="Fetch an approval definition's form and nodes.",
        matches=(
            RestRoute(
                method="GET", path="/open-apis/approval/v4/approvals/{approval_code}"
            ),
        ),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=FeishuAction.APPROVAL_INSTANCE_CREATE,
        normalised_name="Submit an approval",
        description="Create an approval instance (submit a request for approval).",
        matches=(RestRoute(method="POST", path="/open-apis/approval/v4/instances"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=FeishuAction.APPROVAL_INSTANCE_GET,
        normalised_name="Get an approval instance",
        description="Fetch an approval instance's status and timeline.",
        matches=(
            RestRoute(
                method="GET", path="/open-apis/approval/v4/instances/{instance_id}"
            ),
        ),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=FeishuAction.APPROVAL_INSTANCE_TASKS,
        normalised_name="List approval tasks",
        description="List the approval tasks of an instance.",
        matches=(
            RestRoute(
                method="GET",
                path="/open-apis/approval/v4/instances/{instance_id}/tasks",
            ),
        ),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    # ============================== Minutes ==============================
    EndpointSpec(
        id=FeishuAction.MINUTES_LIST,
        normalised_name="List meeting minutes",
        description="List the user's meeting minutes (妙记).",
        matches=(RestRoute(method="GET", path="/open-apis/minutes/v1/minutes"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=FeishuAction.MINUTES_TRANSCRIPT_GET,
        normalised_name="Get minutes transcript",
        description="Fetch a meeting minute's transcript.",
        matches=(
            RestRoute(
                method="GET",
                path="/open-apis/minutes/v1/minutes/{minute_token}/transcript",
            ),
        ),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    # ============================== Search ==============================
    EndpointSpec(
        id=FeishuAction.MESSAGE_SEARCH,
        normalised_name="Search messages",
        description="Search messages the user can see by keyword.",
        matches=(RestRoute(method="POST", path="/open-apis/search/v2/message"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
]


class FeishuProvider(OAuthExternalAppProvider):
    spec = OAuthProviderSpec(
        app_type=ExternalAppType.FEISHU,
        app_name="Feishu",
        oauth=OAuthFlowSpec(
            authorize_url=("https://passport.feishu.cn/suite/passport/oauth/authorize"),
            token_url="https://passport.feishu.cn/suite/passport/oauth/token",
            scope="openid offline_access",
            scope_param="scope",
        ),
        # Feishu's console names the OAuth client credentials app_id/app_secret
        # rather than the RFC-6749 client_id/client_secret.
        client_credential_keys=("app_id", "app_secret"),
        descriptor=AdminDescriptorSpec(
            upstream_url_patterns=["https://open\\.feishu\\.cn/.*"],
            auth_template={"Authorization": "Bearer {access_token}"},
            required_org_credential_fields=[
                OrgCredentialField(
                    key="app_id",
                    label="App ID",
                    description="Feishu app ID (App ID), from the developer console.",
                ),
                OrgCredentialField(
                    key="app_secret",
                    label="App Secret",
                    description="The Feishu app secret. Treat this like a password.",
                    secret=True,
                ),
            ],
            setup_instructions=(
                "In the Feishu developer console (open.feishu.cn), use an "
                "enterprise self-built app: (1) Security settings — add this "
                "Onyx instance's redirect URL /craft/v1/apps/oauth/callback; "
                f"(2) Permissions — grant: {FEISHU_SETUP_PERMISSIONS} "
                "(3) Version management — create and publish a new version so "
                "the permissions take effect. Then paste the App ID and App "
                "Secret below. Each member connects their own account from "
                "/craft/v1/apps via the OAuth popup."
            ),
        ),
        endpoint_catalog=_ENDPOINTS,
    )

    def extract_credentials(self, response_data: dict[str, Any]) -> dict[str, Any]:
        access_token = response_data.get("access_token")
        if not access_token:
            raise OnyxError(
                OnyxErrorCode.BAD_GATEWAY,
                "Feishu OAuth response did not contain an access token.",
            )
        creds: dict[str, Any] = {
            "access_token": access_token,
            "token_type": response_data.get("token_type"),
        }
        if response_data.get("refresh_token"):
            creds["refresh_token"] = response_data["refresh_token"]
        if response_data.get("expires_in"):
            creds["expires_in"] = response_data["expires_in"]
        return creds
