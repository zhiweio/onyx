# IM 机器人部署指南（企微 / 钉钉 / 飞书）

回调端点统一为 `POST {你的域名}/onyxbot/{platform}/callback`（无 `/api` 前缀，nginx 直达 api_server）。
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
4. 验证方式：企微后台点"保存"时平台会发 URL 验证请求，端点解密 echo 明文原样返回。

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
- **去重**：Redis SETNX on msg id（平台会重试回调）。Redis 不可用时丢弃回调（宁可少答不重复答）。
- **用户映射**：确定性邮箱 `{platform}-{platform_user_id}@{email_domain}`，与 SSO 登录同一身份（权限天然一致）；首条消息自动建 BOT 账号并记录 `china_im_binding`。
- **推送**：审批卡片、循环待审产出（LOOP_OUTPUT_HELD）通过绑定表 DM 推送。
- **规模**：单 api_server 进程并发回答上限 8（信号量）；更大规模把回答派发改投 celery（框架已隔离派发函数）。

## 已知边界（后续迭代）

- 目前处理文本消息；图片/富媒体回 ACK 不作答。
- 群频道级 persona 配置（SlackChannelConfig 等价物）未做——所有消息走默认 persona。
- 标准答案短路：管理页与表已就绪，机器人派发路径接入在下一迭代。
