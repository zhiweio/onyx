"""WeCom (企业微信) smart-robot CLI gateway as an org-credential app.

A WeCom smart robot (智能机器人) reaches its enterprise through the CLI gateway
(``https://qyapi.weixin.qq.com/cli``): the org credential is the robot's
``bot_id``/``bot_secret``, exchanged server-side (see
:mod:`onyx.external_apps.org_token`) for a short-lived bearer token that the
egress proxy injects as ``Authorization``. There is no per-user OAuth — the
robot always acts for its authorized human, so org credentials are the only
secret and this is not an :class:`OAuthExternalAppProvider`.

The catalog covers the gateway surface end to end: the five transport
endpoints (the token bootstrap is DENY'd — minting tokens is the proxy's job,
never the agent's) plus every service method the gateway's
``service/discovery`` publishes (calendar, chat, contact, disk, doc, mail,
media, message, meeting, sheet, smartpage, smartsheet, todo, identity). Reads
default ALWAYS, writes ASK, deletes and meeting/schedule cancellations DENY;
anything unmatched on the host falls back to whole-domain ASK via the standard
gate rule.
"""

import json
from typing import Any

from onyx.db.enums import EndpointPolicy, ExternalAppType
from onyx.external_apps.presentation.payload_decoders import PayloadDecoder
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

# The schema paths below are gateway-relative; the wire path carries the /cli
# prefix (e.g. /cli/calendar/schedules/create).
_CLI_PREFIX = "/cli"


class WeComAction(ExternalAppAction):
    """Strongly-typed catalog ids for the WeCom provider."""

    AUTH_BOOTSTRAP = "wecom.auth.bootstrap"
    GATEWAY_DISCOVERY = "wecom.gateway.discovery"
    GATEWAY_TASK_QUERY = "wecom.gateway.task_query"
    GATEWAY_REMOTE_DOC = "wecom.gateway.remote_doc"
    GATEWAY_FILE_UPLOAD = "wecom.gateway.file_upload"
    CALENDAR_SCHEDULES_CANCEL = "wecom.calendar.schedules.cancel"
    CALENDAR_SCHEDULES_CREATE = "wecom.calendar.schedules.create"
    CALENDAR_SCHEDULES_FREE_LIST = "wecom.calendar.schedules.free.list"
    CALENDAR_SCHEDULES_GET = "wecom.calendar.schedules.get"
    CALENDAR_SCHEDULES_LIST = "wecom.calendar.schedules.list"
    CALENDAR_SCHEDULES_SEARCH = "wecom.calendar.schedules.search"
    CALENDAR_SCHEDULES_UPDATE = "wecom.calendar.schedules.update"
    CHAT_GROUPS_LIST = "wecom.chat.groups.list"
    CHAT_MESSAGES_LIST = "wecom.chat.messages.list"
    CONTACT_USERS_SEARCH = "wecom.contact.users.search"
    DISK_FILES_DOWNLOAD = "wecom.disk.files.download"
    DISK_FILES_GET = "wecom.disk.files.get"
    DISK_FILES_LIST = "wecom.disk.files.list"
    DISK_FILES_RENAME = "wecom.disk.files.rename"
    DISK_FILES_SEARCH = "wecom.disk.files.search"
    DISK_FILES_UPLOAD = "wecom.disk.files.upload"
    DISK_FOLDERS_CREATE = "wecom.disk.folders.create"
    DOC_CONTENTS_APPEND = "wecom.doc.contents.append"
    DOC_CONTENTS_GET = "wecom.doc.contents.get"
    DOC_CONTENTS_OVERWRITE = "wecom.doc.contents.overwrite"
    DOC_CREATE = "wecom.doc.create"
    DOC_IMPORT = "wecom.doc.import"
    DOC_MEMBERS_UPDATE = "wecom.doc.members.update"
    DOC_NAMES_UPDATE = "wecom.doc.names.update"
    DOC_RULES_UPDATE = "wecom.doc.rules.update"
    DOC_SEARCH = "wecom.doc.search"
    IDENTITY_WHOAMI = "wecom.identity.whoami"
    MAIL_GET = "wecom.mail.get"
    MAIL_SEARCH = "wecom.mail.search"
    MAIL_SEND = "wecom.mail.send"
    MEDIA_DOWNLOAD = "wecom.media.download"
    MEDIA_UPLOAD = "wecom.media.upload"
    MEETING_CANCEL = "wecom.meeting.cancel"
    MEETING_CREATE = "wecom.meeting.create"
    MEETING_GET = "wecom.meeting.get"
    MEETING_LIST = "wecom.meeting.list"
    MEETING_ORIGINAL_GET = "wecom.meeting.original.get"
    MEETING_ROOMS_BUILDINGS_LIST = "wecom.meeting.rooms.buildings.list"
    MEETING_ROOMS_SEARCH = "wecom.meeting.rooms.search"
    MEETING_SEARCH = "wecom.meeting.search"
    MEETING_UPDATE = "wecom.meeting.update"
    MESSAGE_AIBOT_SEND = "wecom.message.aibot.send"
    MESSAGE_AIBOT_SESSIONS_LIST = "wecom.message.aibot.sessions.list"
    MESSAGE_FILES_GET = "wecom.message.files.get"
    MESSAGE_SEND = "wecom.message.send"
    SHEET_CONTENTS_UPDATE = "wecom.sheet.contents.update"
    SHEET_CREATE = "wecom.sheet.create"
    SHEET_GET = "wecom.sheet.get"
    SHEET_IMPORT = "wecom.sheet.import"
    SHEET_RANGES_GET = "wecom.sheet.ranges.get"
    SHEET_ROWS_APPEND = "wecom.sheet.rows.append"
    SHEET_SUBSHEETS_ADD = "wecom.sheet.subsheets.add"
    SHEET_SUBSHEETS_DELETE = "wecom.sheet.subsheets.delete"
    SMARTPAGE_BLOCKS_UPDATE = "wecom.smartpage.blocks.update"
    SMARTPAGE_CREATE = "wecom.smartpage.create"
    SMARTPAGE_DATABASES_GET = "wecom.smartpage.databases.get"
    SMARTPAGE_FILES_UPLOAD = "wecom.smartpage.files.upload"
    SMARTPAGE_IMAGES_UPLOAD = "wecom.smartpage.images.upload"
    SMARTPAGE_IMPORT = "wecom.smartpage.import"
    SMARTPAGE_PAGES_APPEND = "wecom.smartpage.pages.append"
    SMARTPAGE_PAGES_GET = "wecom.smartpage.pages.get"
    SMARTPAGE_PAGES_OVERWRITE = "wecom.smartpage.pages.overwrite"
    SMARTPAGE_PAGES_UPDATE = "wecom.smartpage.pages.update"
    SMARTSHEET_CHARTS_ADD = "wecom.smartsheet.charts.add"
    SMARTSHEET_CHARTS_DELETE = "wecom.smartsheet.charts.delete"
    SMARTSHEET_CHARTS_LIST = "wecom.smartsheet.charts.list"
    SMARTSHEET_CHARTS_UPDATE = "wecom.smartsheet.charts.update"
    SMARTSHEET_CREATE = "wecom.smartsheet.create"
    SMARTSHEET_FIELDS_ADD = "wecom.smartsheet.fields.add"
    SMARTSHEET_FIELDS_DELETE = "wecom.smartsheet.fields.delete"
    SMARTSHEET_FIELDS_LIST = "wecom.smartsheet.fields.list"
    SMARTSHEET_FIELDS_UPDATE = "wecom.smartsheet.fields.update"
    SMARTSHEET_FILES_UPLOAD = "wecom.smartsheet.files.upload"
    SMARTSHEET_GET = "wecom.smartsheet.get"
    SMARTSHEET_IMAGES_UPLOAD = "wecom.smartsheet.images.upload"
    SMARTSHEET_IMPORT = "wecom.smartsheet.import"
    SMARTSHEET_RECORDS_ADD = "wecom.smartsheet.records.add"
    SMARTSHEET_RECORDS_DELETE = "wecom.smartsheet.records.delete"
    SMARTSHEET_RECORDS_LIST = "wecom.smartsheet.records.list"
    SMARTSHEET_RECORDS_QUERY = "wecom.smartsheet.records.query"
    SMARTSHEET_RECORDS_UPDATE = "wecom.smartsheet.records.update"
    SMARTSHEET_SHEETS_ADD = "wecom.smartsheet.sheets.add"
    SMARTSHEET_SHEETS_DELETE = "wecom.smartsheet.sheets.delete"
    SMARTSHEET_SHEETS_LIST = "wecom.smartsheet.sheets.list"
    SMARTSHEET_SHEETS_UPDATE = "wecom.smartsheet.sheets.update"
    SMARTSHEET_VIEWS_ADD = "wecom.smartsheet.views.add"
    SMARTSHEET_VIEWS_DELETE = "wecom.smartsheet.views.delete"
    SMARTSHEET_VIEWS_LIST = "wecom.smartsheet.views.list"
    SMARTSHEET_VIEWS_UPDATE = "wecom.smartsheet.views.update"
    TODO_CREATE = "wecom.todo.create"
    TODO_DELETE = "wecom.todo.delete"
    TODO_FINISH = "wecom.todo.finish"
    TODO_GET = "wecom.todo.get"
    TODO_LIST = "wecom.todo.list"
    TODO_UPDATE = "wecom.todo.update"


_ENDPOINTS: tuple[EndpointSpec, ...] = (
    EndpointSpec(
        id=WeComAction.AUTH_BOOTSTRAP,
        normalised_name="Exchange bot credentials for a CLI token",
        description="换取 CLI 网关 Bearer token 的引导端点。代理在服务端自行调用；沙箱内直连此端点属于凭据伪造面，默认拒绝。",
        matches=(RestRoute(method="POST", path="/cgi-bin/aibot/cli/get_cli_config"),),
        default_policy=EndpointPolicy.DENY,
    ),
    EndpointSpec(
        id=WeComAction.GATEWAY_DISCOVERY,
        normalised_name="Discover CLI gateway services",
        description="拉取 CLI 网关服务目录与方法 schema。",
        matches=(RestRoute(method="POST", path="/cli/service/discovery"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=WeComAction.GATEWAY_TASK_QUERY,
        normalised_name="Poll an async gateway task",
        description="轮询异步任务（导入、SQL 查询等）的结果。",
        matches=(RestRoute(method="POST", path="/cli/task/query"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=WeComAction.GATEWAY_REMOTE_DOC,
        normalised_name="Fetch remote service documentation",
        description="读取服务的远程渲染文档/帮助/schema。",
        matches=(RestRoute(method="POST", path="/cli/remote_doc/get"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=WeComAction.GATEWAY_FILE_UPLOAD,
        normalised_name="Upload a media file to the gateway",
        description="上传媒体文件（multipart，field=media），返回 media_id。",
        matches=(RestRoute(method="POST", path="/cli/file/upload"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.CALENDAR_SCHEDULES_CANCEL,
        normalised_name="Delete a schedule",
        description="取消（删除）日程，周期日程需指定编辑规则（仅本次、本次及以后、全部）",
        matches=(RestRoute(method="POST", path="/cli/calendar/schedules/cancel"),),
        default_policy=EndpointPolicy.DENY,
    ),
    EndpointSpec(
        id=WeComAction.CALENDAR_SCHEDULES_CREATE,
        normalised_name="Create calendar schedules",
        description="创建日程，支持设置标题、时间、地点、备注、参与人、提醒时间、时区、是否全天等信息",
        matches=(RestRoute(method="POST", path="/cli/calendar/schedules/create"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.CALENDAR_SCHEDULES_FREE_LIST,
        normalised_name="Query shared free/busy slots",
        description="查询指定成员在指定时间范围内的共同空闲时段，返回推荐的空闲时间段列表",
        matches=(RestRoute(method="POST", path="/cli/calendar/schedules/free/list"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=WeComAction.CALENDAR_SCHEDULES_GET,
        normalised_name="Read calendar schedules",
        description="根据日程 ID 批量获取日程详情，返回日程的完整信息：标题、时间、地点、备注、参与人、提醒、时区、周期规则等",
        matches=(RestRoute(method="POST", path="/cli/calendar/schedules/get"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=WeComAction.CALENDAR_SCHEDULES_LIST,
        normalised_name="List calendar schedules",
        description="查询指定时间范围内的日程列表，返回日程的基本信息：标题、开始时间、结束时间、参与人、会议室、地点、备注",
        matches=(RestRoute(method="POST", path="/cli/calendar/schedules/list"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=WeComAction.CALENDAR_SCHEDULES_SEARCH,
        normalised_name="Search calendar schedules",
        description="按关键词搜索指定时间范围内的日程，返回匹配的日程列表（标题、时间、参与人、会议室、地点、备注）",
        matches=(RestRoute(method="POST", path="/cli/calendar/schedules/search"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=WeComAction.CALENDAR_SCHEDULES_UPDATE,
        normalised_name="Update calendar schedules",
        description="更新日程信息（Patch 语义），支持修改标题、时间、地点、备注、新增/移除参与人，周期日程需指定编辑规则",
        matches=(RestRoute(method="POST", path="/cli/calendar/schedules/update"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.CHAT_GROUPS_LIST,
        normalised_name="List chat groups",
        description="按时间范围分页获取有消息的会话列表（目前仅群聊）",
        matches=(RestRoute(method="POST", path="/cli/chat/groups/list"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=WeComAction.CHAT_MESSAGES_LIST,
        normalised_name="List chat messages",
        description="按时间范围分页拉取指定会话的消息列表",
        matches=(RestRoute(method="POST", path="/cli/chat/messages/list"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=WeComAction.CONTACT_USERS_SEARCH,
        normalised_name="Search directory contacts",
        description="通过 keywords 搜索成员信息（open cli场景）",
        matches=(RestRoute(method="POST", path="/cli/contact/users/search"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=WeComAction.DISK_FILES_DOWNLOAD,
        normalised_name="Download a drive file",
        description="异步根据微盘文件 ID 或 URL 下载文件，轮询完成后返回本地文件路径",
        matches=(RestRoute(method="POST", path="/cli/disk/files/download"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=WeComAction.DISK_FILES_GET,
        normalised_name="Read a drive file's metadata",
        description="读取一个微盘文件的基础信息，包含名称、大小、类型、创建者、所属知识空间、所在文件夹、时间与路径等",
        matches=(RestRoute(method="POST", path="/cli/disk/files/get"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=WeComAction.DISK_FILES_LIST,
        normalised_name="List recently viewed drive files",
        description="列出当前用户在微盘中最近浏览过的文件，按最后浏览时间倒序返回，支持分页",
        matches=(RestRoute(method="POST", path="/cli/disk/files/list"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=WeComAction.DISK_FILES_RENAME,
        normalised_name="Rename a drive file",
        description="修改微盘文件的显示名称",
        matches=(RestRoute(method="POST", path="/cli/disk/files/rename"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.DISK_FILES_SEARCH,
        normalised_name="Search drive files",
        description="根据关键词搜索微盘中的文件或文件夹；支持按文件类型、创建者、知识空间过滤，支持排序和分页",
        matches=(RestRoute(method="POST", path="/cli/disk/files/search"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=WeComAction.DISK_FILES_UPLOAD,
        normalised_name="Upload a drive file",
        description="使用 media_id 或本地文件路径将文件上传到微盘指定文件夹，传 file_path 且 file_name 不传时从路径自动提取文件名",
        matches=(RestRoute(method="POST", path="/cli/disk/files/upload"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.DISK_FOLDERS_CREATE,
        normalised_name="Create a drive folder",
        description="在微盘指定父文件夹下新建文件夹，不传 folder_id 时默认创建到个人空间根目录",
        matches=(RestRoute(method="POST", path="/cli/disk/folders/create"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.DOC_CONTENTS_APPEND,
        normalised_name="Append to a Word document",
        description="在 Word 文档末尾追加文本内容",
        matches=(RestRoute(method="POST", path="/cli/doc/contents/append"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.DOC_CONTENTS_GET,
        normalised_name="Read a Word document's content",
        description="读取 Word 文档内容，支持 text 和 ooxml 格式返回",
        matches=(RestRoute(method="POST", path="/cli/doc/contents/get"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=WeComAction.DOC_CONTENTS_OVERWRITE,
        normalised_name="Overwrite a Word document's content",
        description="用新内容全量覆盖 Word 文档的全部内容，原内容将被替换",
        matches=(RestRoute(method="POST", path="/cli/doc/contents/overwrite"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.DOC_CREATE,
        normalised_name="Create doc",
        description="新建文档，支持 doc/sheet/smartsheet 文档类型，可设置初始内容和字段",
        matches=(RestRoute(method="POST", path="/cli/doc/create"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.DOC_IMPORT,
        normalised_name="Import doc",
        description="创建文档导入任务（将外部文件导入为在线文档），也可通过传入 taskid 查询已有导入任务的状态",
        matches=(RestRoute(method="POST", path="/cli/doc/import"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.DOC_MEMBERS_UPDATE,
        normalised_name="Update document collaborators",
        description="添加文档协作成员，设置成员的读写权限",
        matches=(RestRoute(method="POST", path="/cli/doc/members/update"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.DOC_NAMES_UPDATE,
        normalised_name="Rename a document",
        description="重命名指定文档的标题",
        matches=(RestRoute(method="POST", path="/cli/doc/names/update"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.DOC_RULES_UPDATE,
        normalised_name="Update document join rules",
        description="设置文档加入规则，包括是否开启成员加入确认、企业内外成员加入权限",
        matches=(RestRoute(method="POST", path="/cli/doc/rules/update"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.DOC_SEARCH,
        normalised_name="Search doc",
        description="按关键词搜索文档，支持按文档类型、创建者、浏览者、时间范围等多维度过滤，支持排序和分页",
        matches=(RestRoute(method="POST", path="/cli/doc/search"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=WeComAction.IDENTITY_WHOAMI,
        normalised_name="Read the current bot and user identity",
        description="获取当前会话身份, 涵盖机器人和真人双重身份",
        matches=(RestRoute(method="POST", path="/cli/identity/whoami"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=WeComAction.MAIL_GET,
        normalised_name="Read an email",
        description="支持通过encode_mail_id获取邮件信息的接口",
        matches=(RestRoute(method="POST", path="/cli/mail/get"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=WeComAction.MAIL_SEARCH,
        normalised_name="Search emails",
        description="支持搜索邮件和拉取邮件列表",
        matches=(RestRoute(method="POST", path="/cli/mail/search"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=WeComAction.MAIL_SEND,
        normalised_name="Send, reply to, or forward an email",
        description="支持发送、回复和转发邮件的接口，其中发信还支持日程邮件和会议邮件",
        matches=(RestRoute(method="POST", path="/cli/mail/send"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.MEDIA_DOWNLOAD,
        normalised_name="Download media",
        description="根据 media_id 下载媒体文件。",
        matches=(RestRoute(method="POST", path="/cli/media/download"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=WeComAction.MEDIA_UPLOAD,
        normalised_name="Upload media",
        description="上传媒体文件，返回 media_id",
        matches=(RestRoute(method="POST", path="/cli/media/upload"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.MEETING_CANCEL,
        normalised_name="Cancel a meeting",
        description="取消预定会议：周期会议取消单次需指定子会议 ID",
        matches=(RestRoute(method="POST", path="/cli/meeting/cancel"),),
        default_policy=EndpointPolicy.DENY,
    ),
    EndpointSpec(
        id=WeComAction.MEETING_CREATE,
        normalised_name="Create meeting",
        description="创建会议",
        matches=(RestRoute(method="POST", path="/cli/meeting/create"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.MEETING_GET,
        normalised_name="Read meeting",
        description="获取会议详情：标题、开始时间、结束时间、是否全天、时区、会议室、周期规则、参与人列表、会议状态、智能纪要地址、录制文件地址、地点、备注",
        matches=(RestRoute(method="POST", path="/cli/meeting/get"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=WeComAction.MEETING_LIST,
        normalised_name="List meeting",
        description="按时间范围拉取开始时间在对应范围内的会议列表：标题、开始时间、结束时间、参会人数量、时区、会议室、地点、是否是周期会议",
        matches=(RestRoute(method="POST", path="/cli/meeting/list"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=WeComAction.MEETING_ORIGINAL_GET,
        normalised_name="Read a meeting's transcript",
        description="拉取会议转写原文。",
        matches=(RestRoute(method="POST", path="/cli/meeting/original/get"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=WeComAction.MEETING_ROOMS_BUILDINGS_LIST,
        normalised_name="List meeting rooms buildings",
        description="查询企业会议室楼栋信息。",
        matches=(RestRoute(method="POST", path="/cli/meeting/rooms/buildings/list"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=WeComAction.MEETING_ROOMS_SEARCH,
        normalised_name="Search meeting rooms",
        description="查询会议室。",
        matches=(RestRoute(method="POST", path="/cli/meeting/rooms/search"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=WeComAction.MEETING_SEARCH,
        normalised_name="Search meeting",
        description="按关键词搜索会议：支持按关键词匹配会议主题，可选按时间范围过滤，支持 cursor 分页和上翻下翻方向控制。",
        matches=(RestRoute(method="POST", path="/cli/meeting/search"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=WeComAction.MEETING_UPDATE,
        normalised_name="Update meeting",
        description="更新预定会议信息：标题、开始时间、结束时间、参与人、地点、备注",
        matches=(RestRoute(method="POST", path="/cli/meeting/update"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.MESSAGE_AIBOT_SEND,
        normalised_name="Send a bot chat message",
        description="以智能机器人身份向指定单聊/群聊会话发送消息，支持 markdown/图片/文件/语音/视频",
        matches=(RestRoute(method="POST", path="/cli/message/aibot/send"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.MESSAGE_AIBOT_SESSIONS_LIST,
        normalised_name="List message aibot sessions",
        description="获取智能机器人最近的会话列表，按最后一条消息时间倒序返回最多 20 个会话",
        matches=(RestRoute(method="POST", path="/cli/message/aibot/sessions/list"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=WeComAction.MESSAGE_FILES_GET,
        normalised_name="Download a message attachment",
        description="根据消息媒体 ID 获取图片/文件/语音/视频的文件内容",
        matches=(RestRoute(method="POST", path="/cli/message/files/get"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=WeComAction.MESSAGE_SEND,
        normalised_name="Send a chat message",
        description="向指定单聊/群聊会话发送文本消息",
        matches=(RestRoute(method="POST", path="/cli/message/send"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.SHEET_CONTENTS_UPDATE,
        normalised_name="Update sheet contents",
        description="更新表格指定范围的单元格数据",
        matches=(RestRoute(method="POST", path="/cli/sheet/contents/update"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.SHEET_CREATE,
        normalised_name="Create sheet",
        description="新建文档，支持 doc/sheet/smartsheet 文档类型，可设置初始内容和字段",
        matches=(RestRoute(method="POST", path="/cli/sheet/create"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.SHEET_GET,
        normalised_name="Read sheet",
        description="获取表格文档的基本信息，包含工作表列表（sheet_id、标题、行列数等）",
        matches=(RestRoute(method="POST", path="/cli/sheet/get"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=WeComAction.SHEET_IMPORT,
        normalised_name="Import sheet",
        description="创建文档导入任务（将外部文件导入为在线文档），也可通过传入 taskid 查询已有导入任务的状态",
        matches=(RestRoute(method="POST", path="/cli/sheet/import"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.SHEET_RANGES_GET,
        normalised_name="Read sheet ranges",
        description="读取表格指定范围的单元格数据，范围格式遵循 A1 表示法",
        matches=(RestRoute(method="POST", path="/cli/sheet/ranges/get"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=WeComAction.SHEET_ROWS_APPEND,
        normalised_name="Append to sheet rows",
        description="在表格工作表末尾追加一行数据",
        matches=(RestRoute(method="POST", path="/cli/sheet/rows/append"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.SHEET_SUBSHEETS_ADD,
        normalised_name="Add sheet subsheets",
        description="在表格文档中添加新的工作表，可指定标题和插入位置",
        matches=(RestRoute(method="POST", path="/cli/sheet/subsheets/add"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.SHEET_SUBSHEETS_DELETE,
        normalised_name="Delete a spreadsheet worksheet",
        description="删除表格文档中的指定工作表，删除后不可恢复",
        matches=(RestRoute(method="POST", path="/cli/sheet/subsheets/delete"),),
        default_policy=EndpointPolicy.DENY,
    ),
    EndpointSpec(
        id=WeComAction.SMARTPAGE_BLOCKS_UPDATE,
        normalised_name="Update smartpage blocks",
        description="编辑智能页面block(插入/替换/删除)",
        matches=(RestRoute(method="POST", path="/cli/smartpage/blocks/update"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.SMARTPAGE_CREATE,
        normalised_name="Create smartpage",
        description="新建智能页面文档",
        matches=(RestRoute(method="POST", path="/cli/smartpage/create"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.SMARTPAGE_DATABASES_GET,
        normalised_name="Read smartpage databases",
        description="读取数据库信息",
        matches=(RestRoute(method="POST", path="/cli/smartpage/databases/get"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=WeComAction.SMARTPAGE_FILES_UPLOAD,
        normalised_name="Upload smartpage files",
        description="上传文件到文档,得到url",
        matches=(RestRoute(method="POST", path="/cli/smartpage/files/upload"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.SMARTPAGE_IMAGES_UPLOAD,
        normalised_name="Upload smartpage images",
        description="上传文件到文档,得到url",
        matches=(RestRoute(method="POST", path="/cli/smartpage/images/upload"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.SMARTPAGE_IMPORT,
        normalised_name="Import smartpage",
        description="导入 markdown 创建智能页面",
        matches=(RestRoute(method="POST", path="/cli/smartpage/import"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.SMARTPAGE_PAGES_APPEND,
        normalised_name="Append to smartpage pages",
        description="追加内容到页面",
        matches=(RestRoute(method="POST", path="/cli/smartpage/pages/append"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.SMARTPAGE_PAGES_GET,
        normalised_name="Read smartpage pages",
        description="读取智能主页内容",
        matches=(RestRoute(method="POST", path="/cli/smartpage/pages/get"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=WeComAction.SMARTPAGE_PAGES_OVERWRITE,
        normalised_name="Overwrite smartpage pages",
        description="覆盖页面内容",
        matches=(RestRoute(method="POST", path="/cli/smartpage/pages/overwrite"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.SMARTPAGE_PAGES_UPDATE,
        normalised_name="Restructure smart pages",
        description="修改页面(创建/删除/重命名/移动/更新布局)",
        matches=(RestRoute(method="POST", path="/cli/smartpage/pages/update"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.SMARTSHEET_CHARTS_ADD,
        normalised_name="Add smartsheet charts",
        description="修改仪表盘的图表，支持增加图表配置",
        matches=(RestRoute(method="POST", path="/cli/smartsheet/charts/add"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.SMARTSHEET_CHARTS_DELETE,
        normalised_name="Delete a smartsheet chart",
        description="修改仪表盘的图表，支持删除图表配置",
        matches=(RestRoute(method="POST", path="/cli/smartsheet/charts/delete"),),
        default_policy=EndpointPolicy.DENY,
    ),
    EndpointSpec(
        id=WeComAction.SMARTSHEET_CHARTS_LIST,
        normalised_name="List smartsheet charts",
        description="拉取智能表格的图表列表",
        matches=(RestRoute(method="POST", path="/cli/smartsheet/charts/list"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=WeComAction.SMARTSHEET_CHARTS_UPDATE,
        normalised_name="Update smartsheet charts",
        description="修改仪表盘的图表，支持更新图表配置",
        matches=(RestRoute(method="POST", path="/cli/smartsheet/charts/update"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.SMARTSHEET_CREATE,
        normalised_name="Create smartsheet",
        description="新建智能表格文档，支持初始表结构与内容",
        matches=(RestRoute(method="POST", path="/cli/smartsheet/create"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.SMARTSHEET_FIELDS_ADD,
        normalised_name="Add smartsheet fields",
        description="智能表格新增字段",
        matches=(RestRoute(method="POST", path="/cli/smartsheet/fields/add"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.SMARTSHEET_FIELDS_DELETE,
        normalised_name="Delete a smartsheet field",
        description="智能表格删除字段",
        matches=(RestRoute(method="POST", path="/cli/smartsheet/fields/delete"),),
        default_policy=EndpointPolicy.DENY,
    ),
    EndpointSpec(
        id=WeComAction.SMARTSHEET_FIELDS_LIST,
        normalised_name="List smartsheet fields",
        description="拉取智能表格的字段列表",
        matches=(RestRoute(method="POST", path="/cli/smartsheet/fields/list"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=WeComAction.SMARTSHEET_FIELDS_UPDATE,
        normalised_name="Update smartsheet fields",
        description="智能表格更新字段",
        matches=(RestRoute(method="POST", path="/cli/smartsheet/fields/update"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.SMARTSHEET_FILES_UPLOAD,
        normalised_name="Upload smartsheet files",
        description="上传文件到文档,得到url",
        matches=(RestRoute(method="POST", path="/cli/smartsheet/files/upload"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.SMARTSHEET_GET,
        normalised_name="Read smartsheet",
        description="获取智能表格的基本信息，包含子表列表（子表 ID、名称、类型、行列数、前五列信息等）",
        matches=(RestRoute(method="POST", path="/cli/smartsheet/get"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=WeComAction.SMARTSHEET_IMAGES_UPLOAD,
        normalised_name="Upload smartsheet images",
        description="上传文件到文档,得到url",
        matches=(RestRoute(method="POST", path="/cli/smartsheet/images/upload"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.SMARTSHEET_IMPORT,
        normalised_name="Import smartsheet",
        description="导入 xlsx 创建智能表格",
        matches=(RestRoute(method="POST", path="/cli/smartsheet/import"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.SMARTSHEET_RECORDS_ADD,
        normalised_name="Add smartsheet records",
        description="批量新增智能表格行记录",
        matches=(RestRoute(method="POST", path="/cli/smartsheet/records/add"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.SMARTSHEET_RECORDS_DELETE,
        normalised_name="Delete smartsheet records",
        description="批量删除智能表格行记录",
        matches=(RestRoute(method="POST", path="/cli/smartsheet/records/delete"),),
        default_policy=EndpointPolicy.DENY,
    ),
    EndpointSpec(
        id=WeComAction.SMARTSHEET_RECORDS_LIST,
        normalised_name="List smartsheet records",
        description="读取智能表格数据，支持读取字段定义(fields)、图表(charts)、视图(views)、记录(records)，支持排序、过滤和分页",
        matches=(RestRoute(method="POST", path="/cli/smartsheet/records/list"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=WeComAction.SMARTSHEET_RECORDS_QUERY,
        normalised_name="Query smartsheet data with SQL",
        description="通过 SQL 查询仪表盘数据，支持异步轮询；首次请求 task_id 为空，data_initing=true 时按 task_id 重试",
        matches=(RestRoute(method="POST", path="/cli/smartsheet/records/query"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=WeComAction.SMARTSHEET_RECORDS_UPDATE,
        normalised_name="Upsert smartsheet records",
        description="批量增加/更新/删除智能表格记录（行数据）",
        matches=(RestRoute(method="POST", path="/cli/smartsheet/records/update"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.SMARTSHEET_SHEETS_ADD,
        normalised_name="Add smartsheet sheets",
        description="智能表格新增子表",
        matches=(RestRoute(method="POST", path="/cli/smartsheet/sheets/add"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.SMARTSHEET_SHEETS_DELETE,
        normalised_name="Delete a smartsheet sub-sheet",
        description="智能表格删除子表",
        matches=(RestRoute(method="POST", path="/cli/smartsheet/sheets/delete"),),
        default_policy=EndpointPolicy.DENY,
    ),
    EndpointSpec(
        id=WeComAction.SMARTSHEET_SHEETS_LIST,
        normalised_name="List smartsheet sheets",
        description="获取智能表格的基本信息，包含子表列表（子表 ID、名称、类型、行列数、前五列信息等）",
        matches=(RestRoute(method="POST", path="/cli/smartsheet/sheets/list"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=WeComAction.SMARTSHEET_SHEETS_UPDATE,
        normalised_name="Update smartsheet sheets",
        description="修改智能表格结构，支持增加/更新/删除子表和列字段",
        matches=(RestRoute(method="POST", path="/cli/smartsheet/sheets/update"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.SMARTSHEET_VIEWS_ADD,
        normalised_name="Add smartsheet views",
        description="修改智能表格视图，增加视图配置",
        matches=(RestRoute(method="POST", path="/cli/smartsheet/views/add"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.SMARTSHEET_VIEWS_DELETE,
        normalised_name="Delete a smartsheet view",
        description="修改智能表格视图，支持删除视图配置",
        matches=(RestRoute(method="POST", path="/cli/smartsheet/views/delete"),),
        default_policy=EndpointPolicy.DENY,
    ),
    EndpointSpec(
        id=WeComAction.SMARTSHEET_VIEWS_LIST,
        normalised_name="List smartsheet views",
        description="拉取智能表格的视图列表",
        matches=(RestRoute(method="POST", path="/cli/smartsheet/views/list"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=WeComAction.SMARTSHEET_VIEWS_UPDATE,
        normalised_name="Update smartsheet views",
        description="修改智能表格视图，支持更新视图配置",
        matches=(RestRoute(method="POST", path="/cli/smartsheet/views/update"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.TODO_CREATE,
        normalised_name="Create todo",
        description="机器人视角批量创建待办",
        matches=(RestRoute(method="POST", path="/cli/todo/create"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.TODO_DELETE,
        normalised_name="Delete todos",
        description="机器人视角批量删除待办",
        matches=(RestRoute(method="POST", path="/cli/todo/delete"),),
        default_policy=EndpointPolicy.DENY,
    ),
    EndpointSpec(
        id=WeComAction.TODO_FINISH,
        normalised_name="Complete todo",
        description="机器人视角批量完成待办",
        matches=(RestRoute(method="POST", path="/cli/todo/finish"),),
        default_policy=EndpointPolicy.ASK,
    ),
    EndpointSpec(
        id=WeComAction.TODO_GET,
        normalised_name="Read todo",
        description="批量读取待办详情，返回标题/描述/参与人/时间等",
        matches=(RestRoute(method="POST", path="/cli/todo/get"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=WeComAction.TODO_LIST,
        normalised_name="List todo",
        description="读取机器人为创建人、对话人为参与人选的待办列表（按 update_time 降序），返回标题/描述/人名",
        matches=(RestRoute(method="POST", path="/cli/todo/list"),),
        default_policy=EndpointPolicy.ALWAYS,
    ),
    EndpointSpec(
        id=WeComAction.TODO_UPDATE,
        normalised_name="Update todo",
        description="机器人视角批量更新待办（标题/描述/参与人/截止时间等）",
        matches=(RestRoute(method="POST", path="/cli/todo/update"),),
        default_policy=EndpointPolicy.ASK,
    ),
)


class _PayloadStringDecoder:
    """Unwrap the CLI gateway's ``{"payload": "<json-string>"}`` envelope so an
    approval card shows the inner request object instead of an escaped string.
    Fails open to the raw payload (the decoder contract)."""

    def decode(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw = payload.get("payload")
        if not isinstance(raw, str):
            return payload
        try:
            inner = json.loads(raw)
        except ValueError:
            return payload
        if isinstance(inner, dict) and set(payload) == {"payload"}:
            return inner
        return {**payload, "payload": inner}


_PAYLOAD_DECODER = _PayloadStringDecoder()


class WeComProvider(ExternalAppProvider):
    """WeCom via the smart-robot CLI gateway: org credentials only, with a
    derived org-level bearer token injected at egress (``org_token``)."""

    spec = ProviderSpec(
        app_type=ExternalAppType.WECOM,
        app_name="WeCom",
        descriptor=AdminDescriptorSpec(
            upstream_url_patterns=["https://qyapi\\.weixin\\.qq\\.com/.*"],
            auth_template={"Authorization": "Bearer {access_token}"},
            required_org_credential_fields=[
                OrgCredentialField(
                    key="bot_id",
                    label="Bot ID",
                    description=(
                        "The smart robot's Bot ID, from the WeCom client's "
                        "robot config (智能机器人 → API 配置)."
                    ),
                ),
                OrgCredentialField(
                    key="bot_secret",
                    label="Bot Secret",
                    description=(
                        "The smart robot's secret. Treat this like a password."
                    ),
                    secret=True,
                ),
            ],
            setup_instructions=(
                "In the WeCom client (not the admin console): 工作台 → 智能机器人 "
                "→ 创建机器人 → API 配置 → 使用长连接, then paste the shown Bot ID "
                "and Secret below. The gateway serves messages, docs, sheets, "
                "smartsheets, smartpages, mail, calendar, meetings, todo, drive "
                "(disk), media, and contacts; the egress proxy exchanges these "
                "credentials for a bearer token and never sends the secret to "
                "the sandbox. Message receiving (长连接/回调) is a separate IM-bot "
                "surface configured on the WeCom SSO provider."
            ),
        ),
        endpoint_catalog=list(_ENDPOINTS),
        org_token=OrgTokenSpec(
            kind="wecom_cli",
            credential_keys=("bot_id", "bot_secret"),
        ),
    )

    def payload_decoders(self) -> dict[str, PayloadDecoder]:
        # The gateway wraps every JSON body as {"payload": "<json>"}; unwrap it
        # for approval display across the whole catalog.
        return {action.value: _PAYLOAD_DECODER for action in WeComAction}
