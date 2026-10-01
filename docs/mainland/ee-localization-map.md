# EE 功能本地化对照表

本仓库（mainland 分支）是仅含社区版（CE）的商用基线：`backend/ee`、`web/src/app/ee`、`web/src/ee` 已物理删除。
Enterprise Edition 功能按下表处理：已本地化重实现（按公开规格，非抄源码）、或有明确的替代物、或明确不做。

| EE 功能 | 处理 | 替代物 / 位置 |
|---|---|---|
| 用户组管理 API + UI | ✅ 重实现 | `onyx/db/user_group_ce.py`、`/manage/admin/user-group`（页面 `GroupsPage` 原本就在） |
| SSO（SAML/OIDC 之外的中国生态） | ✅ 重实现（超集） | `onyx/server/china_sso.py`：企微/钉钉/飞书/WPS365 扫码，OIDC/SAML 上游 CE 自带 |
| 组织架构/部门同步 | ✅ 新建 | 登录时平台部门 → 用户组（`assign_user_to_groups_by_name`）：企微/钉钉/飞书走各自通讯录 API（失败降级为空，不阻断登录）；WPS365 无稳定开放通讯录 API，明确降级不同步 |
| 文档级权限同步（外部源） | ✅ 新建（部分） | CE runner 已填实：`onyx/background/celery/tasks/doc_permission_syncing/`（beat 每小时巡检、每日每连接器同步一次；`element_update_permissions` 落 PG + 刷索引 ACL）；SharePoint 沿用上游连接器实现；飞书 wiki 成员列表 → 外部邮箱/组（不可读时降级私有 ACL）。企微微盘/钉钉知识库/WPS365 的 perm-sync 未实现（平台 API 受限，按「只索引不同步权限」降级） |
| SCIM 用户供给 | ❌ 不做 | 中国部署用 SSO + 组织架构同步替代（Okta/Azure 场景不存在） |
| 多租户（tenants） | ❌ 不做 | 产品形态是单租户私有化部署 |
| 计费 / 许可证（billing/license） | ❌ 不做 | 私有化无 SaaS 计费；`LICENSE_ENFORCEMENT_ENABLED` 默认已翻转为 false |
| Token 速率限制管理 API + 页 | ✅ 重实现 | 执行层与 DAL 本就在 CE（`db/token_limit.py`）；本分支补 `/admin/token-rate-limits` 路由并挂上原本 90% 完成的面板 |
| 标准答案（客服快捷回复） | ✅ 重实现 | 表本就在 CE；本分支补管理 API + `/admin/standard-answers` 页；Slack 与中国 IM 机器人的短路路径可读 |
| 查询历史 / analytics 报表 | ✅ 最小集替代 | `/admin/audit` 的查询历史标签页（SearchQuery 表 + 分页过滤 API），不重建 EE analytics 全家桶 |
| 审计（工具调用/MCP/审批） | ✅ 新建 | `platform_tool_log` 表 + 审计页五标签 |
| 自定义品牌（logo/theme） | ⏭ 可选后置 | 低优先级；需要时走 `Settings` 表加 logo 字段 |
| Evals 评估 | ❌ 不做 | 场景质量由 CraftJobEvent + 审计页覆盖；GA 后再评估 |
| 日志导出 | ❌ 不做 | 私有化部署日志进客户自己的基础设施 |
| Vespa 索引 | ❌ 不做 | `ONYX_DISABLE_VESPA=true` 纯 OpenSearch |

红线：重实现一律从公开规格出发（行为/接口/文档），不参考、不翻译 ee 源码；分发镜像不得携带任何 ee 内容。

## 后置待办（按客户需求排期）

本轮明确后置的中国化项：

- 搜索供应商管理化：博查/百度目前仅环境变量选择（`WEB_SEARCH_PROVIDER`），未纳入管理页 web_search provider 模型。
- 邮件 / 阿里云短信通知通道（当前通知环内 + IM 卡片）。
- WPS 预览服务接入（当前用本地 docx/xlsx/pptx 查看器）。
- 阿里云内容安全接入 content_screen enforce 模式（当前为正则启发式）。
- 爬虫回调入 RAG（当前 crawl 仅直给 agent，不入索引）。
- 记忆 scope 化双笔记本（当前仅作业级 MEMORY.md）。
- MCP 网关连接池化（当前每调用短连接；SDK 的 ClientSessionGroup 可用）。
- 定时任务 run 级 interrupt（当前仅任务级暂停与作业级取消）。
- IM 内联审批按钮回传（当前审批卡片带深链回 web 审批页）。
- 企微微盘 / 钉钉知识库 / WPS365 的 perm-sync（平台 API 能力确认后再做）。
- WPS365 组织架构同步（无稳定开放通讯录 API）。
