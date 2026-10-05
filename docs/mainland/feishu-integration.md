# 飞书集成部署指南(SSO / 连接器 / 机器人)

本文档记录在 Onyx(mainland 分支)上完成飞书三件套集成的完整流程,按 2026-10 实际部署验证。
应用侧配置均在飞书开放平台(open.feishu.cn)的企业自建应用上完成;Onyx 侧只需要一行 SSO Provider 配置。

## 0. 前置条件

- 飞书企业管理员账号(版本发布与可用范围需要管理员身份)。
- Onyx 服务在跑(api_server / background / web_server)。
- 机器人事件回调需要公网可达的 HTTPS 地址;本地开发用 `ngrok http 8080` 打隧道。

## 1. 飞书开放平台应用配置

以应用「onyx」(App ID `cli_aa4bed8882389bdd`)为例。

### 1.1 凭证

「凭证与基础信息」页取 `App ID` 与 `App Secret`(Secret 点眼睛图标显示)。

### 1.2 添加能力

「添加应用能力」→ 添加「机器人」。

### 1.3 权限管理(全部为免审权限)

| Scope | 身份 | 用途 |
|---|---|---|
| `contact:user.base:readonly` | 应用 + 用户 | SSO 部门同步 / ACL 邮箱解析 |
| `contact:user.email:readonly` | 应用 + 用户 | SSO 登录授权页申请邮箱(userinfo 返回 email 的前提) |
| `contact:department.base:readonly` | 应用 | SSO 部门同步 |
| `contact:contact.base:readonly` | 应用 | 按部门列成员(机器人身份映射/测试) |
| `wiki:wiki:readonly` | 应用 | 连接器:列知识库空间/节点 |
| `wiki:wiki` | 应用 | (仅测试造数需要)创建空间/节点 |
| `docx:document:readonly` | 应用 | 连接器:读文档纯文本 |
| `docx:document` | 应用 | (仅测试造数需要)写文档块 |
| `drive:drive:readonly` | 应用 | 连接器:云盘目录/文件下载 + 权限成员(ACL) |
| `im:message` | 应用 | 机器人:发消息 |
| `im:message.group_msg` | 应用 | 连接器:读取群历史消息(2026-10 实测所需权限名,缺它报 230027) |
| `im:message.p2p_msg:readonly` | 应用 | 机器人:接收单聊事件 |
| `im:message.group_at_msg:readonly` | 应用 | 机器人:接收群@事件 |
| `im:message.group_at_msg.include_bot:readonly` | 应用 | 机器人:接收含其他机器人群的@事件 |
| `im:chat:readonly` | 应用 | 机器人:群信息;连接器:群列表/群成员(ACL) |
| `task:tasklist:read` | 应用 | 连接器:任务清单读取(缺它报 99991672) |
| `task:task:read` | 应用 | 连接器:任务读取 |

### 1.4 事件与回调

1. 「事件与回调」→「事件配置」→ 订阅方式选 **将事件发送至开发者服务器**。
2. 请求地址填 `https://<公网域名>/onyxbot/feishu/callback`(本地开发填 ngrok 地址)。
   保存时飞书会 POST `url_verification`(带 `challenge`),Onyx 校验 token 后回显即通过。
3. 「加密策略」→ `Verification Token` 点重置后明文显示,记下来(`Encrypt Key` 可不开,Onyx 兼容无加密模式)。
4. 「添加事件」→ 搜索「接收消息」→ 订阅 `im.message.receive_v1`(应用身份)。

### 1.5 安全设置

「安全设置」→「重定向 URL」添加:

```
http://localhost:3000/api/auth/china/callback
```

`localhost` 的 http 地址是允许的;生产环境填 `https://<你的域名>/api/auth/china/callback`。

### 1.6 管理后台(admin.feishu.cn)

- 「应用管理」→ onyx → 可用范围改为**全体成员**(部分成员模式下通讯录数据权限不覆盖根部门,
  `contact/v3/users/find_by_department` 会报 `40004 no dept authority`,连接器的邮箱解析同样受影响)。

### 1.7 发布版本

「版本管理与发布」→「创建版本」→ 填更新说明 → 保存 → 确认发布。
**每次改权限/事件/回调都要发新版本才生效**(免审核的可用范围下提交即上线)。

## 2. 知识库授权给应用(连接器必需)

应用身份(tenant token)只能看到**自己是成员/管理员的知识空间**。官方推荐做法
([知识库常见问题 #3](https://open.feishu.cn/document/ukTMukTMukTM/uUDN04SN0QjL1QDN/wiki-v2/wiki-qa)):

- 方式一(客户端):飞书客户端建群把机器人拉进群 → 知识库「设置 → 成员设置」把该群加为管理员/成员。
- 方式二(API):管理员 user_access_token 调 `POST /wiki/v2/spaces/{space_id}/members`,
  `member_type=openid`、`member_id=<应用 open_id>`(`GET /bot/v3/info` 可取)、`member_role=admin`。

注意:创建知识空间(`POST /wiki/v2/spaces`)**不支持应用身份**,只能用户身份调用。

## 3. Onyx 侧配置

### 3.1 SSO Provider(机器人凭据也在这里)

管理后台 → SSO → 新建,或直接调 API:

```jsonc
POST /api/admin/sso/provider
{
  "name": "feishu",
  "display_name": "飞书",
  "provider_type": "FEISHU",
  "config": {
    "app_id": "cli_...",
    "app_secret": "...",
    "bot_verification_token": "<1.4 步取得的 Verification Token>",
    "email_domain": "feishu.local"   // 平台不回邮箱时的确定性身份兜底域
  },
  "allowed_email_domains": []
}
```

保存后登录页出现「飞书」按钮;`/api/auth/type` 的 `sso_providers` 里出现 `authorize_url`。
SSO 授权页会申请 `contact:user.base:readonly` + `contact:user.email:readonly`
(见 `china_sso.FEISHU_LOGIN_SCOPES`),userinfo 拿不到 email 时回退 `{union_id}@{email_domain}`。

### 3.2 机器人

无需额外配置:凭据就在 3.1 的 Provider 行上,presence 即启用。
事件回调 URL 已在 1.4 配好。私聊机器人发消息即可问答;`/场景 <名称> <任务>` 可触发 Craft。

### 3.3 连接器

飞书按能力拆成 4 个源,凭据都填同一份 `feishu_app_id` / `feishu_app_secret`
(同一应用,无需在飞书后台建多个应用):

| 源 | 分类 | 索引内容 | 专属配置 |
|---|---|---|---|
| `feishu` | 知识库与 Wiki | 知识空间 → 节点树 → docx 正文 | 无 |
| `feishu_drive` | 云存储 | 云盘文件夹(默认应用根目录,可配 `root_folder_tokens`);docx 走纯文本导出,sheet/bitable 导出 CSV,上传文件下载后走标准解析 | 根目录 token 列表 |
| `feishu_im` | 即时通讯 | 机器人所在群聊历史,按群×天成档(默认近 90 天,可配) | `history_days`、`chat_ids` |
| `feishu_task` | 任务工单 | 任务清单 → 任务(参与者解析成 ACL) | 无 |

保存时 `validate_connector_settings` 会实际调飞书校验(坏密钥→凭据错误;缺对应
权限→权限错误)。前置条件:

- 知识空间/云盘目录:应用需被加入对应空间(见第 2 节)。
- 群聊历史:机器人必须在目标群里;不在的群读不到。
- ACL 邮箱解析:应用可用范围需覆盖成员(见 1.6)。

### 3.4 Craft 外部应用（/admin/craft/apps）

Craft 的 agent 在沙箱里以**用户身份**实时调飞书 Open API(读+写),与连接器的
应用身份定时索引互补。管理后台 /admin/craft/apps → 添加「Feishu」,组织凭据填同一份
`app_id` / `app_secret`;每个成员在 /craft/v1/apps 用 OAuth 连自己的账号。

动作目录(58 个)覆盖 IM、文档(docx)、知识库(wiki)、云盘(drive)、电子表格、
多维表格(bitable)、任务、日历、通讯录、审批、妙记、消息搜索。默认策略:读=ALWAYS、
创建/发送/更新=ASK(沙箱里逐次审批)、删除=DENY,管理员可逐项改。

需要的权限(均免审,改完必须发新版本):

| 域 | Scope |
|---|---|
| IM | `im:message`、`im:message:readonly`、`im:chat`、`im:chat:readonly`、`im:resource`(消息资源下载) |
| 文档 | `docx:document`、`docx:document:readonly` |
| 知识库 | `wiki:wiki`、`wiki:wiki:readonly` |
| 云盘 | `drive:drive`、`drive:drive:readonly` |
| 电子表格 | `sheets:spreadsheet`、`sheets:spreadsheet:readonly` |
| 多维表格 | `bitable:app`、`bitable:app:readonly` |
| 任务 | `task:task`、`task:task:readonly` |
| 日历 | `calendar:calendar`、`calendar:calendar:readonly` |
| 通讯录 | `contact:user.base:readonly`、`contact:contact.base:readonly` |
| 审批 | `approval:approval`、`approval:approval:readonly`(若免审列表搜不到则跳过该域) |
| 妙记 | `minutes:minutes:readonly` |
| 搜索 | 控制台搜「搜索」按需开(消息搜索/文档搜索) |

安全设置 → 重定向 URL 需包含 `http://localhost:3000/craft/v1/apps/oauth/callback`
(生产换真实域名)。令牌刷新/续期由 Onyx 代理层自动处理(passport 标准 OAuth2,
refresh token 轮转)。

## 4. 中国平台能力矩阵(连接器分类覆盖)

| 平台 | 知识库与 Wiki | 云存储 | 即时通讯 | 任务工单 |
|---|---|---|---|---|
| 飞书 | `feishu` ✅ | `feishu_drive` ✅ | `feishu_im` ✅ | `feishu_task` ✅ |
| 钉钉 | `dingtalk` ✅ | `dingtalk_drive` ✅(需 operator unionId,待联调验证) | ❌ 无群历史消息开放 API | `dingtalk_todo` ⚠️ 用户级(待办 API 按 unionId 查询) |
| 企业微信 | `wecom` ✅(微盘即其知识库,同一连接器跨两类展示) | `wecom` ✅ | ❌ 仅付费「会话存档」有历史消息(需 license + C SDK,不做) | `wecom_approval` ✅(OA 审批单当工单,待联调验证) |
| WPS 365 | `wps365` ✅(云文档即其知识库,同一连接器跨两类展示) | `wps365` ✅ | ❌ 无消息 API | ❌ 无任务 API |

## 5. 端到端验证清单

1. **SSO**:登录页点「飞书」→ 授权 → 回跳进入 `/app`;`oauth_account` 表新增
   `oauth_name='feishu'` 的关联。
2. **连接器**:知识空间建文档 → 等 celery 索引(`index_attempt.status=SUCCESS`,
   `document_by_connector_credential_pair.has_been_indexed=t`)→ `/api/admin/search`
   能检索到,`semantic_identifier` 形如 `知识空间/文档名`。
3. **机器人**:`POST /onyxbot/feishu/callback` 模拟 `im.message.receive_v1`(header.token 填
   Verification Token)→ 几秒后飞书里收到 LLM 回复;`china_im_binding` 表有绑定记录。

## 6. 本地开发的已知限制

- ngrok 免费版每次重启域名会变,需同步更新飞书后台的回调地址;生产请用固定域名。
- 容器部署时改代码需 `docker cp` 进 `onyx-api_server-1` / `onyx-background-1` 后重启
  (镜像未挂载源码),或重建镜像。
- 组织通讯录未绑邮箱时,SSO 用户与机器人用户的确定性邮箱不同
  (`on_<union_id>@…` vs `feishu-<open_id>@…`),属预期;绑定真实邮箱后二者按 email 关联。
