# IM 机器人部署指南（企微 / 钉钉 / 飞书）

回调端点统一为 `POST {你的域名}/onyxbot/{platform}/callback`（无 `/api` 前缀，nginx 直达 api_server）。
企微的 URL 验证握手走 `GET` 同一路径；钉钉/飞书的验证走 POST（GET 返回 405，属预期）。
机器人凭据**不单独配置**：直接写在对应的 SSO Provider 行上（管理后台 → SSO），presence 即启用。

## 1. 企业微信（wecom）

1. 企业微信管理后台 → 应用管理 → 创建自建应用，拿到 `CorpID`、`Secret`、`AgentId`。
2. 应用的"接收消息"设置里：
   - URL 填 `https://你的域名/onyxbot/wecom/callback`
   - 生成 Token 与 EncodingAESKey
3. 在 Onyx 管理后台创建 WECOM 类型 SSO Provider，配置：
   - `corp_id` / `corp_secret` / `agent_id`
   - `bot_token`、`bot_encoding_aes_key`（第 2 步生成的两个值）
   - `email_domain`（如 `corp.example.cn`——平台不返回邮箱时构造确定性身份）
4. 验证方式：企微后台点"保存"时平台发 **GET** URL 验证请求（query 携带 `msg_signature`/`timestamp`/`nonce`/`echostr`），端点验签解密 `echostr` 后明文原样返回。

## 2. 钉钉（dingtalk）

1. 钉钉开放平台 → 应用开发 → 企业内部应用 → 机器人，开启"消息接收模式 = HTTP 模式"。
2. 消息接收地址填 `https://你的域名/onyxbot/dingtalk/callback`，生成 aesKey。
3. 记下 `robotCode`（机器人编码）与应用的 `AppKey`/`AppSecret`。
4. Onyx 侧 DINGTALK Provider 配置：`client_id`/`client_secret`/`robot_code`/`bot_aes_key`/`email_domain`。
5. URL 验证：平台发送解密后为 `success` 的密文，端点回加密的 `success`。

## 3. 飞书（feishu）

1. 飞书开放平台 → 企业自建应用 → 添加"机器人"能力。
2. 事件与回调 → 订阅方式选"将事件发送至开发者服务器"：
   - 请求地址 `https://你的域名/onyxbot/feishu/callback`
   - 记下 Verification Token 与 Encrypt Key
3. 订阅事件：`im.message.receive_v1`（接收消息）。
4. Onyx 侧 FEISHU Provider 配置：`app_id`/`app_secret`/`bot_verification_token`/`bot_encrypt_key`/`email_domain`。
5. URL 验证：端点校验 token 后回显 `challenge`。

## 行为说明

- **认证**：无会话登录——每平台的签名/解密验证即认证（企微 SHA1 签名+corp 校验、钉钉 AES、飞书 token）。
- **应答时限**：平台要求 1-5 秒内回 200。端点内联完成验签/去重/URL 验证；真正回答在后台线程（进程内聊天引擎），答复通过平台 API 异步回发。
- **多轮上下文**：每个 (平台, 用户) 复用最近一个会话，多轮对话共享上下文；发 `/reset`（或 `/新对话`）开启新会话。注意 Onyx 的用户长期记忆（memory 表）跨会话生效，重置会话不会清除已提取的记忆。
- **飞书流式回答**：飞书先回一张"正在思考…"交互卡片，生成过程中按 1.5s 节流原地更新卡片，完成时定格全文；超过 3500 字的卡片放不下的部分以纯文本消息补发。企微/钉钉仍为完成后单条回复。
- **飞书 markdown 渲染**：所有飞书回复（含命令直回与推送）均以交互卡片发送并用 markdown 模块渲染；发卡前做语法转换——`#` 标题转粗体、GFM 表格转"**列名**: 值"键值列表、HTML（`<br>`/`<a>`/`<b>` 等）转对应 markdown、其余尖括号转全角、分隔线转"———"。代码块、列表、引用、链接原样透传。卡片 markdown 不支持表格与标题语法，故需转换。
- **去重**：Redis SETNX on msg id（平台会重试回调）。Redis 不可用时丢弃回调（宁可少答不重复答）。
- **用户映射与权限**：每条消息先做身份解析——飞书 open_id → 通讯录 API 取 union_id → `oauth_account`（SSO 登录时写入的 `feishu:{app_id}:{union_id}`）→ 真实 Onyx 账号。解析成功即以本人身份运行对话与场景，**场景/技能可见性、文档 ACL 与网页端完全一致**；未做过 SSO 登录的用户回退确定性影子账号 `{platform}-{platform_user_id}@{email_domain}`（仅能看到公开资源），首次 SSO 登录后自动切换并保留会话绑定。
- **chat / craft 边界**：IM 是轻量入口。默认走 Onyx chat（检索问答）；`/场景` 与菜单以显式命令触发 Craft 任务，服务端执行，进度/审批/产出通过绑定表 DM 推送并带 Web 深链——IM 侧不做长任务承载。
- **推送**：审批请求、内容隔离、循环待审产出（LOOP_OUTPUT_HELD）、场景任务完成报告，均通过绑定表 DM 推送（带 `/craft/v1?sessionId=...` 深链；站点域名由部署侧可知）。
- **场景触发**：聊天中发送 `/场景 <名称> <任务内容>`（或 `/scenario ...`）即以当前用户身份启动 CraftJob。场景名称按"可见即有权"匹配（最长前缀，支持含空格的名称）；未授权/未找到会得到拒绝回复。任务进度、审批与产出到深链会话里查看。
- **自定义菜单**：悬浮菜单样式(需飞书客户端 7.22+),四个入口全部绑定机器人命令——「新对话」「技能」「我的场景」「使用帮助」,点击即以菜单文案为消息内容触发对应命令。菜单在控制台「机器人 → 机器人自定义菜单」配置,需发布版本后约 5 分钟生效。
- **技能**:`/技能` 列出最近更新的技能,`/技能 <关键词>` 按名称/描述搜索,`/技能 <序号>` 选中后下一条消息携带该技能执行(30 分钟内有效),`/取消技能` 取消。可见性与 Web 端一致(可见即有权)。注意:当前 chat 侧技能注入仅对内置技能生效,自定义技能与 Web 行为一致会被跳过。
- **附件**:先发图片/文件(可连续多个,≤10 个),再发文字说明,附件随文字一并进入 chat/技能管线;大小上限与管理端 `user_file_max_upload_size_mb` 一致,类型遵循 Onyx MIME 白名单。场景任务遇到附件:转存为用户文件并在回复中提示(Craft 沙箱直接读取用户文件在后续迭代)。
- **并发限额**:每用户从 IM 启动的场景任务同时最多 `im_craft_job_concurrency_limit` 个(管理后台 → IM 机器人 页可配,默认 2,Web 端不受限)。超限时拒绝并列出运行中任务;`/我的任务` 查看,`/取消任务 <序号>` 释放额度;任务失败也会 IM 推送。
- **规模**：单 api_server 进程并发回答上限 8（信号量）；更大规模把回答派发改投 celery（框架已隔离派发函数）。

## 已知边界（后续迭代）

- 目前处理文本消息；图片/富媒体回 ACK 不作答。
- 群频道级 persona 配置（SlackChannelConfig 等价物）未做——所有消息走默认 persona。
- 标准答案短路：管理页与表已就绪，机器人派发路径接入在下一迭代。
