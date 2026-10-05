# 企业微信集成部署指南 (SSO / 连接器 / 智能机器人 / IM 机器人)

本文档记录在 Onyx (mainland 分支) 上完成企业微信四件套集成的完整流程,按 2026-10
实际部署验证 (企业 `ww2b7698f2e68481e7` 上海睿当家)。企业微信侧分两个身份面:

- **经典自建应用** (corp_id/corp_secret/agent_id): 承载 SSO 登录、IM 机器人回调、
  微盘与审批等经典 `cgi-bin` API (需要可信 IP + 备案域名);
- **智能机器人 + CLI 网关** (bot_id/bot_secret): 承载 Craft 沙箱的治理动作目录
  (`https://qyapi.weixin.qq.com/cli`,签名换 Bearer,不要求备案域名/可信 IP),
  同时支撑 wecom_docs / wecom_im 两个网关版连接器。

## 0. 前置条件

- 企业微信管理员 (自建应用创建、回调配置需要)。
- 企业微信桌面客户端 (智能机器人只能在客户端创建,管理后台没有入口)。
- Onyx 服务在跑 (api_server / background / sandbox-proxy)。
- IM 机器人回调需要公网 HTTPS;本地开发 `ngrok http 8080` 只能用来联调
  Onyx 侧处理器,企业微信侧保存会被拒 (见 1.3)。

## 1. 企业微信侧配置

### 1.1 经典自建应用 (SSO + IM 机器人 + 经典连接器)

管理后台 (work.weixin.qq.com) → 应用管理 → 自建 → 创建应用:

- 记录 `AgentId`;「我的企业 → 企业信息」记录 `企业ID (corp_id)`;
  应用页点「查看」取 `Secret`。
- 「企业微信授权登录」→ 设置授权回调域 (SSO 登录用)。
- 「网页授权及JS-SDK」→ 设置可信域名 (需域名归属认证)。
- 「企业可信IP」→ 配置服务器出口 IP。**注意:配置可信 IP 前必须先设置可信域名
  或接收消息服务器 URL**,两者都要求备案主体与企业一致。
- 「审批接口」→ 设置开启 (wecom_approval 连接器需要 OA 审批数据权限)。

### 1.2 智能机器人 (CLI 网关, Craft 治理动作 + 网关连接器)

企业微信客户端 → 工作台 → 智能机器人 → 创建机器人:

1. 选择 **API 配置 → 使用长连接** (无需域名/IP;URL 回调模式需要备案域名)。
2. 配置可见范围,保存后页面展示 `Bot ID` 与 `Secret`,妥善保存。
3. 机器人对数据面授权范围的约束 (服务端下发):
   写操作仅允许在线文档/在线表格/智能表格/智能文档四类跨身份,
   其余品类只能写机器人自己创建或拥有的数据;读跟随授权真人。

### 1.3 备案域名硬约束 (2026-10 实测)

以下配置全部要求**备案主体与当前企业相同或有关联关系**的域名,
ngrok/隧道域名会被拒绝 ("该域名主体为第三方服务商,请使用企业主体域名"):

- 接收消息服务器 URL (IM 机器人回调,`https://<域名>/onyxbot/wecom/callback`);
- 网页授权可信域名;
- 企业微信授权登录回调域;
- 企业可信 IP (以上两者未配置时无法保存)。

因此:经典面的活体验证 (SSO 登录回跳、IM 回调、微盘/审批连接器) 只能在持有
备案域名的环境完成;开发环境可验证代码路径 (单测 + 回调处理器),生产按本节配置。
智能机器人 CLI 网关不受此约束,可先行全链路验证。

## 2. Onyx 侧配置

### 2.1 SSO Provider (同时承载 IM 机器人凭据)

管理后台 → SSO 提供商 → 添加,类型选 **WeCom**:

```jsonc
POST /api/admin/sso/provider
{
  "name": "wecom",
  "display_name": "企业微信",
  "provider_type": "WECOM",
  "config": {
    "corp_id": "ww...",             // 企业ID
    "corp_secret": "...",           // 自建应用 Secret
    "agent_id": "1000002",          // 自建应用 AgentId
    "bot_token": "...",             // 可选:接收消息回调 Token (1.3 通过后填)
    "bot_encoding_aes_key": "...",  // 可选:接收消息回调 EncodingAESKey
    "email_domain": "example.com"   // WeCom 不返回邮箱时的兜底 {userid}@domain
  }
}
```

回调 URL 填 `https://<备案域名>/onyxbot/wecom/callback`,GET 握手由
`onyxbot_china_api.py` 解密回显;可见范围建议全体成员。

### 2.2 Craft 外部应用 (智能机器人 CLI 网关)

管理后台 → Craft → 应用 → 添加内置应用 **WeCom**,填智能机器人的
`bot_id` / `bot_secret`。等价 API:

```jsonc
POST /api/build/admin/apps/built-in
{
  "name": "WeCom",
  "app_type": "WECOM",
  "upstream_url_patterns": ["https://qyapi\\.weixin\\.qq\\.com/.*"],
  "auth_template": {"Authorization": "Bearer {access_token}"},
  "organization_credentials": {"bot_id": "aibn...", "bot_secret": "..."}
}
```

治理目录共 **100 个动作**:5 个传输端点 (`auth.bootstrap` DENY、
`gateway.discovery`/`gateway.task_query`/`gateway.remote_doc` ALWAYS、
`gateway.file_upload` ASK) + 网关 `service/discovery` 发布的全部 14 个服务方法
(calendar/chat/contact/disk/doc/mail/media/message/meeting/sheet/smartpage/
smartsheet/todo/identity)。约定与飞书一致:读 ALWAYS、写 ASK、删除与
取消日程/会议 DENY;目录外请求按整域 ASK 兜底。

鉴权:egress 代理用组织凭据在服务端执行
`POST /cgi-bin/aibot/cli/get_cli_config` (sha256(secret+bot_id+time+nonce) 签名)
换取 Bearer token,Redis 缓存 (默认 3000s,无 expires_in),沙箱永不接触密钥;
token 失效 (errcode 853004/853005) 由代理重新派生。沙箱侧通过内置 skill
`wecom` 的 `wecom_api.py` 调用 (`services` 发现 → `call`/`raw`/`upload`)。

### 2.3 连接器 (对照飞书四件套)

| 企业微信连接器 | 凭据 | 对照飞书 | 说明 |
|---|---|---|---|
| `wecom` (微盘) | corp_id/corp_secret | feishu_drive | 经典 wedrive API,需可信 IP |
| `wecom_approval` (审批) | corp_id/corp_secret | — | 经典 OA 审批 API,需可信 IP |
| `wecom_docs` (在线文档) | wecom_bot_id/secret | feishu (wiki/docs) | CLI 网关;`keywords` 搜索发现 + `doc_ids` 直指;doc→markdown, sheet→CSV, smartsheet→记录, smartpage→页面 |
| `wecom_im` (群消息) | wecom_bot_id/secret | feishu_im | CLI 网关;**平台限制仅最近 7 天**;按群按天 (CST) 建文档;无成员 API,无外部 ACL |

网关版连接器没有 ACL API,文档可见性由连接器-凭据对的 access_type 管控
(与 wecom_approval 相同)。`wecom_im` 需要把机器人拉进群聊后才有数据。

## 3. CLI 网关协议要点 (排障用)

- 所有业务请求 `POST {base}{path}`,body 为
  `{"payload": "<JSON 字符串>"}`,带 `Authorization: Bearer <token>`;
  响应 HTTP 200 + `{"errcode", "errmsg", "results_json"}`,业务结果在
  `results_json` 里 (常为双层嵌套 JSON 字符串,需剥两层)。
- 响应含 `taskid` 时表示长任务,以 `long_task_poll.done` 为终止信号
  (mode-1 轮询中 taskid 恒为同一个,不能拿它判断完成):
  `poll_mode=1` (常见) 用**原端点** + 空 JSON body + `X-Long-Poll-TaskId`
  头轮询;`poll_mode=0` 用 `POST /task/query`,body 为 payload 信封包裹的
  `{"method": "PollClawLongTask", "payload": "{\"taskid\": ...}"}`。
  done 后:mode-1 的业务载荷就是响应体本身,mode-0 在 `result` 字段里。
- errcode 853004/853005 = token 失效,重新走 bootstrap;10014 = 轮询方式
  或 taskid 不对 (mode-1 任务不能走 /task/query)。
- 响应里的 `security_notice` / `extra_identity_context` 是平台注入的元数据
  (含提示注入防御文案),按元数据处理,不当作用户内容。

## 4. 2026-10 部署实录

- 自建应用 **Onyx** (AgentId `1000002`),SSO Provider 已建 (`wecom`,
  email_domain `shrdj.com`);回调因无备案域名未保存 (见 1.3)。
- 智能机器人 **Onyx** (Bot ID `aibnWNOyhhhZhCIf9V_S85XeRBhYRjgpWRv`,
  长连接模式)。
- Craft 外部应用 WeCom 已建,100 动作目录生效;容器内实测:
  签名 bootstrap → Bearer 注入 → `identity/whoami` errcode=0。
- 通过网关创建真实在线文档「Onyx 联测文档」
  (`w3_AK8AcHhwADwCNz3Z36nUuQBWjUVFt_a`),`wecom_docs` 连接器
  (`keywords=["Onyx联测"]`) 实跑索引成功 (发现 → markdown 内容 221 字);
  `wecom_im` 校验通过 (机器人尚未入群,0 文档)。
- 待办:机器人拉进群聊后 wecom_im 开始产出;生产域名就绪后按 1.3 补回调/
  可信域名/可信 IP,再启用 IM 机器人与经典连接器。
