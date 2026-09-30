# EE 功能本地化对照表

本仓库（mainland 分支）是仅含社区版（CE）的商用基线：`backend/ee`、`web/src/app/ee`、`web/src/ee` 已物理删除。
Enterprise Edition 功能按下表处理：已本地化重实现（按公开规格，非抄源码）、或有明确的替代物、或明确不做。

| EE 功能 | 处理 | 替代物 / 位置 |
|---|---|---|
| 用户组管理 API + UI | ✅ 重实现 | `onyx/db/user_group_ce.py`、`/manage/admin/user-group`（页面 `GroupsPage` 原本就在） |
| SSO（SAML/OIDC 之外的中国生态） | ✅ 重实现（超集） | `onyx/server/china_sso.py`：企微/钉钉/飞书/WPS365 扫码，OIDC/SAML 上游 CE 自带 |
| 组织架构/部门同步 | ✅ 新建 | 登录时企微部门 → 用户组（`assign_user_to_groups_by_name`） |
| 文档级权限同步（外部源） | ⏭ 延后 | CE 侧框架缝隙已定位；中国连接器（飞书/企微/钉钉/WPS365）先做内容索引，权限同步后续按公开规格实现 |
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
