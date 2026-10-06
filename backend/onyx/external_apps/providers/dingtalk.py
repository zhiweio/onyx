"""DingTalk (钉钉) new-gen OpenAPI as an org-credential app.

An enterprise internal app reaches DingTalk through ``https://api.dingtalk.com``
with the corp ``client_id``/``client_secret`` (AppKey/AppSecret) exchanged
server-side (see :mod:`onyx.external_apps.org_token`) for a short-lived access
token the egress proxy injects as ``x-acs-dingtalk-access-token``. There is no
per-user OAuth — the new-gen REST surface authenticates corp-wide (unionId /
userId ride as path or query parameters), so org credentials are the only
secret and this is not an :class:`OAuthExternalAppProvider`. The legacy
``oapi.dingtalk.com`` host (query-param ``access_token``) is deliberately out
of scope: the header template can't authenticate it.

The catalog covers the new-gen surfaces the deployment's granted permission
points allow: knowledge base (docs) reads, drive (钉盘) reads, todo, calendar,
contacts, robot sends, and AI-card streaming. Reads default ALWAYS, sends and
creates/updates ASK, deletes DENY; the token endpoints are DENY'd outright —
minting tokens is the proxy's job, never the agent's. Anything unmatched on
the host falls back to whole-domain ASK via the standard gate rule.
"""

from onyx.db.enums import EndpointPolicy, ExternalAppType
from onyx.external_apps.providers.actions import (
    EndpointSpec,
    ExternalAppAction,
    RestRoute,
)
from onyx.external_apps.providers.base import (
    AdminDescriptorSpec,
    ExternalAppProvider,
    OrgCredentialField,
    OrgTokenSpec,
    ProviderSpec,
)


class DingTalkAction(ExternalAppAction):
    """Strongly-typed catalog ids for the DingTalk provider."""

    AUTH_CORP_TOKEN = "dingtalk.auth.corp_token"
    AUTH_USER_TOKEN = "dingtalk.auth.user_token"
    KB_LIST = "dingtalk.kb.list"
    KB_NODES_LIST = "dingtalk.kb.nodes.list"
    KB_NODE_CONTENT_GET = "dingtalk.kb.node_content.get"
    DRIVE_SPACES_LIST = "dingtalk.drive.spaces.list"
    DRIVE_FILES_LIST = "dingtalk.drive.files.list"
    DRIVE_FILE_DOWNLOAD = "dingtalk.drive.file.download"
    TODO_TASKS_LIST = "dingtalk.todo.tasks.list"
    TODO_TASK_GET = "dingtalk.todo.task.get"
    TODO_TASK_CREATE = "dingtalk.todo.task.create"
    TODO_TASK_UPDATE = "dingtalk.todo.task.update"
    TODO_TASK_DELETE = "dingtalk.todo.task.delete"
    CALENDAR_EVENTS_LIST = "dingtalk.calendar.events.list"
    CALENDAR_EVENT_GET = "dingtalk.calendar.event.get"
    CALENDAR_EVENT_CREATE = "dingtalk.calendar.event.create"
    CALENDAR_EVENT_UPDATE = "dingtalk.calendar.event.update"
    CALENDAR_EVENT_DELETE = "dingtalk.calendar.event.delete"
    CONTACT_USER_GET = "dingtalk.contact.user.get"
    CONTACT_USERS_SEARCH = "dingtalk.contact.users.search"
    ROBOT_O2O_SEND = "dingtalk.robot.o2o.send"
    ROBOT_GROUP_SEND = "dingtalk.robot.group.send"
    ROBOT_FILE_DOWNLOAD = "dingtalk.robot.file.download"
    CARD_INSTANCE_CREATE = "dingtalk.card.instance.create"
    CARD_INSTANCE_DELIVER = "dingtalk.card.instance.deliver"
    CARD_STREAMING_UPDATE = "dingtalk.card.streaming.update"


_ENDPOINTS: tuple[EndpointSpec, ...] = (
    EndpointSpec(
        id=DingTalkAction.AUTH_CORP_TOKEN,
        normalised_name="Exchange app credentials for an access token",
        description="换取企业 accessToken 的端点。代理在服务端自行调用；沙箱内直连此端点属于凭据伪造面，默认拒绝。",
        matches=(RestRoute(method="POST", path="/v1.0/oauth2/accessToken"),),
        default_policy=EndpointPolicy.DENY,
    ),
    EndpointSpec(
        id=DingTalkAction.AUTH_USER_TOKEN,
        normalised_name="Exchange an OAuth code for a user access token",
        description="用户授权码换用户 accessToken 的端点。代理不使用用户 token；默认拒绝。",
        matches=(RestRoute(method="POST", path="/v1.0/oauth2/userAccessToken"),),
        default_policy=EndpointPolicy.DENY,
    ),
    # ── 知识库（钉钉文档 wiki）───────────────────────────────────────────
    EndpointSpec(
        id=DingTalkAction.KB_LIST,
        normalised_name="List wiki workspaces",
        description="列出操作者可见的知识库（wiki 工作区），需 operatorId（unionId）参数。",
        matches=(RestRoute(method="GET", path="/v2.0/wiki/workspaces"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=DingTalkAction.KB_NODES_LIST,
        normalised_name="List knowledge base nodes",
        description="分页列出知识库某父节点下的子节点（文档/文件夹），需 operatorId 与 parentNodeId。",
        matches=(RestRoute(method="GET", path="/v2.0/wiki/nodes"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=DingTalkAction.KB_NODE_CONTENT_GET,
        normalised_name="Read a knowledge base document",
        description="按块读取知识库文档内容（doc suites blocks），需 operatorId。",
        matches=(
            RestRoute(method="GET", path="/v1.0/doc/suites/documents/{docKey}/blocks"),
        ),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    # ── 云盘（钉盘）─────────────────────────────────────────────────────
    EndpointSpec(
        id=DingTalkAction.DRIVE_SPACES_LIST,
        normalised_name="List drive spaces",
        description="列出云盘空间（需 unionId 参数）。",
        matches=(RestRoute(method="GET", path="/v1.0/drive/spaces"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=DingTalkAction.DRIVE_FILES_LIST,
        normalised_name="List drive files",
        description="分页列出云盘空间/文件夹下的文件。",
        matches=(RestRoute(method="GET", path="/v1.0/drive/spaces/{spaceId}/files"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=DingTalkAction.DRIVE_FILE_DOWNLOAD,
        normalised_name="Get a drive file download URL",
        description="获取云盘文件的下载地址。",
        matches=(
            RestRoute(
                method="GET",
                path="/v1.0/drive/spaces/{spaceId}/files/{fileId}/downloadUrl",
            ),
        ),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    # ── 待办 ────────────────────────────────────────────────────────────
    EndpointSpec(
        id=DingTalkAction.TODO_TASKS_LIST,
        normalised_name="List todo tasks",
        description="分页列出指定用户（unionId）的待办任务。",
        matches=(RestRoute(method="GET", path="/v1.0/todo/users/{unionId}/tasks"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=DingTalkAction.TODO_TASK_GET,
        normalised_name="Read a todo task",
        description="读取单条待办任务详情。",
        matches=(
            RestRoute(method="GET", path="/v1.0/todo/users/{unionId}/tasks/{taskId}"),
        ),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=DingTalkAction.TODO_TASK_CREATE,
        normalised_name="Create a todo task",
        description="为指定用户创建待办任务。",
        matches=(RestRoute(method="POST", path="/v1.0/todo/users/{unionId}/tasks"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=DingTalkAction.TODO_TASK_UPDATE,
        normalised_name="Update a todo task",
        description="更新待办任务（含完成状态）。",
        matches=(
            RestRoute(method="PUT", path="/v1.0/todo/users/{unionId}/tasks/{taskId}"),
        ),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=DingTalkAction.TODO_TASK_DELETE,
        normalised_name="Delete a todo task",
        description="删除待办任务，不可恢复。",
        matches=(
            RestRoute(
                method="DELETE", path="/v1.0/todo/users/{unionId}/tasks/{taskId}"
            ),
        ),
        default_policy=EndpointPolicy.DENY,
    ),
    # ── 日历（日程）─────────────────────────────────────────────────────
    EndpointSpec(
        id=DingTalkAction.CALENDAR_EVENTS_LIST,
        normalised_name="List calendar events",
        description="查询用户主日历某时间段的日程列表。",
        matches=(
            RestRoute(
                method="GET",
                path="/v1.0/calendar/users/{userId}/calendars/{calendarId}/events",
            ),
        ),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=DingTalkAction.CALENDAR_EVENT_GET,
        normalised_name="Read a calendar event",
        description="查询单个日程详情。",
        matches=(
            RestRoute(
                method="GET",
                path=(
                    "/v1.0/calendar/users/{userId}/calendars/{calendarId}"
                    "/events/{eventId}"
                ),
            ),
        ),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=DingTalkAction.CALENDAR_EVENT_CREATE,
        normalised_name="Create a calendar event",
        description="在用户日历上创建日程。",
        matches=(
            RestRoute(
                method="POST",
                path="/v1.0/calendar/users/{userId}/calendars/{calendarId}/events",
            ),
        ),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=DingTalkAction.CALENDAR_EVENT_UPDATE,
        normalised_name="Update a calendar event",
        description="修改日程内容或时间。",
        matches=(
            RestRoute(
                method="PUT",
                path=(
                    "/v1.0/calendar/users/{userId}/calendars/{calendarId}"
                    "/events/{eventId}"
                ),
            ),
        ),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=DingTalkAction.CALENDAR_EVENT_DELETE,
        normalised_name="Delete a calendar event",
        description="删除日程，参与者的日历上同步移除。",
        matches=(
            RestRoute(
                method="DELETE",
                path=(
                    "/v1.0/calendar/users/{userId}/calendars/{calendarId}"
                    "/events/{eventId}"
                ),
            ),
        ),
        default_policy=EndpointPolicy.DENY,
    ),
    # ── 通讯录 ──────────────────────────────────────────────────────────
    EndpointSpec(
        id=DingTalkAction.CONTACT_USER_GET,
        normalised_name="Read a user's contact profile",
        description="按 unionId 查询用户通讯录信息。",
        matches=(RestRoute(method="GET", path="/v1.0/contact/users/{unionId}"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=DingTalkAction.CONTACT_USERS_SEARCH,
        normalised_name="Search users",
        description="按关键词搜索企业内用户。",
        matches=(RestRoute(method="POST", path="/v1.0/contact/users/search"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    # ── 机器人 / AI 卡片 ────────────────────────────────────────────────
    EndpointSpec(
        id=DingTalkAction.ROBOT_O2O_SEND,
        normalised_name="Send a robot direct message",
        description="机器人给指定用户发单聊消息。",
        matches=(RestRoute(method="POST", path="/v1.0/robot/oToMessages/batchSend"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=DingTalkAction.ROBOT_GROUP_SEND,
        normalised_name="Send a robot group message",
        description="机器人在指定群聊里发消息。",
        matches=(RestRoute(method="POST", path="/v1.0/robot/groupMessages/send"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=DingTalkAction.ROBOT_FILE_DOWNLOAD,
        normalised_name="Download a robot-received file",
        description="按 downloadCode 获取机器人收到文件的下载地址。",
        matches=(RestRoute(method="POST", path="/v1.0/robot/messageFiles/download"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=DingTalkAction.CARD_INSTANCE_CREATE,
        normalised_name="Create a card instance",
        description="创建卡片实例（含 AI 流式卡片）。",
        matches=(RestRoute(method="POST", path="/v1.0/card/instances"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=DingTalkAction.CARD_INSTANCE_DELIVER,
        normalised_name="Deliver a card instance",
        description="把卡片实例投递到会话（群聊/单聊）。",
        matches=(RestRoute(method="POST", path="/v1.0/card/instances/deliver"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=DingTalkAction.CARD_STREAMING_UPDATE,
        normalised_name="Stream a card's content",
        description="对流式卡片做增量内容更新。",
        matches=(RestRoute(method="PUT", path="/v1.0/card/streaming"),),
        default_policy=EndpointPolicy.ASK,
    ),
)


class DingTalkProvider(ExternalAppProvider):
    """DingTalk via the new-gen OpenAPI: org credentials only, with a derived
    corp access token injected at egress (``org_token``)."""

    spec = ProviderSpec(
        app_type=ExternalAppType.DINGTALK,
        app_name="DingTalk",
        descriptor=AdminDescriptorSpec(
            upstream_url_patterns=["https://api\\.dingtalk\\.com/.*"],
            auth_template={"x-acs-dingtalk-access-token": "{access_token}"},
            required_org_credential_fields=[
                OrgCredentialField(
                    key="client_id",
                    label="Client ID (AppKey)",
                    description=(
                        "The app's AppKey from the DingTalk developer console "
                        "(应用凭证 → Client ID)."
                    ),
                ),
                OrgCredentialField(
                    key="client_secret",
                    label="Client Secret (AppSecret)",
                    description="The app's AppSecret. Treat this like a password.",
                    secret=True,
                ),
            ],
            setup_instructions=(
                "In the DingTalk developer console (open-dev.dingtalk.com): open "
                "your enterprise internal app, grant the permission points the "
                "catalog uses (contacts, docs/knowledge base, drive, todo, "
                "calendar, robot), add the Onyx server's egress IP under 安全设置, "
                "then paste the Client ID (AppKey) and Client Secret below. The "
                "egress proxy exchanges these credentials for a short-lived "
                "access token and never sends the secret to the sandbox."
            ),
        ),
        endpoint_catalog=list(_ENDPOINTS),
        org_token=OrgTokenSpec(
            kind="dingtalk_corp",
            credential_keys=("client_id", "client_secret"),
            response_token_key="accessToken",
            response_expires_key="expireIn",
        ),
    )
