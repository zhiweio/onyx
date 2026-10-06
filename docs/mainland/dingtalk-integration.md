# 钉钉（DingTalk）集成指南

对标飞书/企微的四块能力：索引连接器、Craft 应用集成（org token）、SSO 登录、IM 机器人（AI 卡片流式回复）。
一个企业内部应用同时承载全部能力；应用凭证只进 Onyx 配置，不进代码库。

## 1. 控制台配置（open-dev.dingtalk.com → 应用开发 → 企业内部应用）

### 1.1 权限管理（权限点按 code 搜索后勾选 → 批量申请，均为免审）

| 权限点 | 用途 |
| --- | --- |
| `Contact.User.Read` | SSO 登录取用户信息（`/v1.0/contact/users/me`） |
| `qyapi_get_member` / `qyapi_get_department_list` / `qyapi_get_department_member` / `fieldEmail` | SSO 部门同步 + 联系人查询 |
| `Wiki.Workspace.Read` / `Wiki.Node.Read` | 知识库（钉钉文档）连接器与 craft 读取 |
| `Document.WorkspaceDocument.Read` | 知识库文档按块读取（doc suites blocks） |
| `Drive.Space.Read` + `Storage.File.Read` + `Storage.DownloadInfo.Read` | 钉盘连接器与 craft 读取 |
| `Todo.Todo.Read` / `Todo.Todo.Write` | 待办连接器与 craft 读写 |
| `Calendar.Event.Read` / `Calendar.Event.Write` | 日程读取与 craft 读写 |
| `qyapi_robot_sendmsg` | 机器人发消息（单聊/群聊） |
| `Card.Instance.Write` / `Card.Streaming.Write` | AI 卡片创建/投递/流式更新 |

### 1.2 安全设置

- **IP 白名单**：填 Onyx 服务器的公网出口 IP。
- **重定向 URL**：填 `{WEB_DOMAIN}/api/auth/china/callback`（SSO 回调；本地调试可另加 `http://localhost:3000/api/auth/china/callback`）。

### 1.3 机器人（应用能力 → 机器人）

推荐**消息接收模式 = Stream 模式**（控制台默认推荐）：无需公网回调地址，
Onyx 的 api_server 启动时会通过 `dingtalk-stream` SDK 建立出站 WebSocket
连接（日志可见 `dingtalk stream client started`），控制台「事件订阅」页会显示
已连接Stream · 在线。**应用发布的前提是存在已接入的推送通道**——Stream 客户端
在线即满足；HTTP 模式则需要回调地址通过平台的公网校验（自建隧道常因浏览器
UA 拦截页而校验失败，报"消息接收地址校验失败/请填写公网可访问的POST地址"）。

HTTP 模式（备选）：消息接收地址填 `https://你的域名/onyxbot/dingtalk/callback`；
「事件订阅 → 订阅管理」推送方式切 HTTP推送 并填同一地址，生成 aes_key/token
后同步写入 Onyx（见 §2.1），保存触发 `check_url` 校验。裸 GET 探测须返回 200。

记下 `robotCode`（企业内部应用通常等于 AppKey）。

### 1.4 应用发布

版本管理与发布 → 创建版本（版本描述、可见范围）→ 发布。若平台提示
"Please fill in the POST address accessible on the public network"：确认 §1.3 的两处
HTTP 配置均已保存且通道验证通过（保存时出现"修改成功"）；个别情况下需要
重新保存机器人配置或人工再点一次发布。

### 1.5 AI 卡片模板（卡片平台，AI 卡片流式回复需要）

1. 开发者平台 → 卡片平台 → 模板管理 → 新建模板 → 类型选 **AI 卡片**。
2. 模板变量必须包含：
   - `msgContent`（String）：回复正文，markdown 渲染；
   - `flowStatus`（String）：流式状态，协议约定 `2`=输出中，`3`=已完成，`5`=失败。
3. 卡片主体放一个 markdown/text 元素绑定 `msgContent`，保存模板后复制模板 ID。
4. 把模板 ID 写入 Onyx 钉钉 SSO Provider 的 `bot_card_template_id`（见 §2.1）。
   不配置该字段时机器人退回「完成后单条纯文本」。

## 2. Onyx 侧配置

### 2.1 SSO Provider（管理后台 → SSO，或 sso_provider 表）

| 字段 | 值 |
| --- | --- |
| `client_id` / `client_secret` | 应用凭证（AppKey/AppSecret） |
| `email_domain` | 平台不返回邮箱时构造确定性身份（如 `corp.example.cn`） |
| `robot_code` | 机器人编码（缺省回退 client_id） |
| `bot_aes_key` | §1.3 生成的加密 aes_key（存储加密） |
| `bot_token` | §1.3 生成的签名 token（选填，填了则校验回调签名；存储加密） |
| `bot_card_template_id` | §1.5 的卡片模板 ID（选填，填了启用 AI 卡片流式回复） |

### 2.2 连接器（管理后台 → 连接器）

三个连接器共用 `{dingtalk_client_id, dingtalk_client_secret}` 凭证：

- **钉钉知识库**（`dingtalk`）：索引知识库 wiki 工作区文档；需配置
  `dingtalk_operator_union_id`（wiki API 要求 operatorId，取管理员的
  unionId，可在开发者后台「通讯录」用户详情查看）。文档正文走
  `GET /v1.0/doc/suites/documents/{docKey}/blocks` 按块拼装。
- **钉钉云盘**（`dingtalk_drive`）：索引钉盘文件；需配置 `operator_union_id`。
- **钉钉待办**（`dingtalk_todo`）：索引指定用户待办；需配置 `operator_union_id`。

> 平台限制：钉钉不开放群聊历史消息 API（自建应用只能实时收到 @机器人 的消息），
> 因此没有对标飞书/企微的 IM 历史回溯连接器。

### 2.3 Craft 应用集成（管理后台 → Craft 应用）

- 应用类型选 **DINGTALK**，填 `client_id` / `client_secret`。org token 由服务端派生
  （`POST /v1.0/oauth2/accessToken`，缓存 ~7100s），沙箱代理注入
  `x-acs-dingtalk-access-token`，密钥永不下发沙箱。
- 沙箱内置技能 `dingtalk`（`dingtalk_api.py`）：`routes` 列出全部路由，
  `call <route> --data '<json>'` 调用（`--paginate` 自动翻页），`raw` 兜底。
  catalog 覆盖：知识库读、云盘读、待办、日历、通讯录、机器人发送（ASK）、
  AI 卡片（ASK）；token 端点与删除类操作默认 DENY，未匹配请求落整域 ASK。
- 注意：企业 token 没有「我」的概念——个人云盘/待办/日历需先 `contact.search`
  定位用户拿 unionId/userId，或向用户确认。

## 3. 回调协议要点（`POST /onyxbot/dingtalk/callback`）

- **签名**（配置 `bot_token` 时校验）：query 的 `signature`/`timestamp`/`nonce`，
  算法 = SHA-1(sorted(token, timestamp, nonce, encrypt))，与企微同族。
- **URL 存活探测**：裸 GET 须返回 200。
- **通道验证**：POST 解密得 `{"EventType":"check_url"}`；响应须为
  `{"msg_signature", "timeStamp", "nonce", "encrypt"}`，其中 `encrypt` 是用
  aes_key 加密的 `success`，**信封后缀必须是 AppKey**（平台解密后校验后缀），
  `msg_signature` 为响应四元组的排序 SHA-1。
- **消息事件**：解密后 JSON 携带 `senderStaffId`/`conversationId`/`conversationType`
  （"1"=单聊，"2"=群聊）/`text.content`；群消息在群内回复，单聊走机器人私信。

## 4. 已知限制

- 群聊历史不可回溯索引（见 §2.2）。
- 机器人 HTTP 回调地址变更后需重新保存并发布应用版本。
- ngrok 等隧道域名重启会变化，需同步更新控制台两处回调地址。

## 4.1 快捷指令提示（钉钉没有点击发命令的原生菜单）

钉钉机器人不支持飞书式悬浮菜单（单聊快捷入口 API 打开的是网页而非发命令，
且其常驻入口价值与工作台网页应用重复）。Onyx 的替代：

- 每条回复（AI 卡片与纯文本）尾部附加快捷指令行：
  `🆕 新对话 · 📋 场景列表 · 🧰 技能 · ❓ 帮助（回复文字即可）`。
- 这些文字与飞书菜单文案同为命令别名，直接回复即触发。
- 后续迭代（可选）：自建 AI 卡片模板带 `actionType=request` 按钮，点击经
  stream topic `/v1.0/card/instances/callback` 回来合成命令 —— 依赖卡片
  平台模板发布。

## 5. 端到端验证清单（2026-10-06 实测）

| 场景 | 验证方式 | 结果 |
| --- | --- | --- |
| Bot 凭据 | 管理端 `POST /api/admin/onyxbot-china/dingtalk/verify` | ✅ |
| 单聊 AI 卡片流式 | 模拟加密回调（真实 staffId）；AI 卡片走官方公共模板 | ✅ `china_im_binding` 落库、卡片帧全部 200 |
| 卡片模板 | 卡片平台 AI 卡片；自建模板未发布时可用官方公共模板 ID `02fcf2f4-5e02-4a85-b672-46d1f715543e.schema` | ✅ 写入 `bot_card_template_id` |
| Craft 应用 | craft 会话调 `dingtalk_api.py kb.list` | ✅ proxy 门控 `dingtalk.kb.list policy=ALWAYS` + org token 注入，真实返回知识库 |
| 知识库连接器 | UI 配置（凭据=AppKey/Secret，连接器配置=operator_union_id）→ 同步 | ✅ 抓取 9 篇、blocks 正文完整；向量写入见下方环境说明 |
| SSO 扫码登录 | 登录页点钉钉 → 扫码授权 | ✅ `oauth_account` 落库（unionId 确定性邮箱） |
| 真机消息（Stream 通道） | 钉钉客户端发消息/群内 @机器人 | ✅ Stream 接收 → AI 卡片流式回复，无错误日志 |

> **环境已知问题（非钉钉专属）**：本部署的 `indexing_model_server` 实际加载
> `thenlper/gte-small`（384 维），而全部 `search_settings` 与 opensearch 既有索引
> 按 768 维（nomic）声明/创建。docprocessing 写向量时维度不匹配 → 所有连接器
> （含飞书/企微）的向量写入同样失败。恢复需统一嵌入模型并全量重建索引。
> 机器人 Stream 通道：api_server 启动即连（`dingtalk stream client started`），
> 控制台事件订阅页显示 已连接Stream · 在线。
