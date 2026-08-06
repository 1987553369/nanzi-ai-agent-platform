# NanZi 项目记忆库

> 审计基线：`main@70e490c4bf47e6577f3665029b2ad5abc1bfe951`，2026-08-06。
> 本文是项目长期上下文入口；完整清单见 [`docs/memory/`](docs/memory/README.md)。

## 1. 项目概览

NanZi 是一套面向企业内部业务的智能体运行与治理平台。后端采用 Python 3.11、FastAPI、SQLAlchemy 2 异步 ORM、AgentScope 2，前端采用 Vue 3、TypeScript、Vite 与 Tailwind；平台主库支持 MySQL/PostgreSQL，Redis Stack 同时承载会话、缓存、分布式锁、运行状态和向量索引。产品已覆盖 ChatBI、知识问答、Agent/Prompt/Skill/MCP 管理、任务调度、报表订阅、个人工作台和 iframe Embed。当前最合适的定位是“可嵌入、可追溯、基于企业真实数据与知识执行任务的可信业务智能体平台”，而不是通用聊天壳或全能低代码平台。

静态盘点规模：约 1,700 个文件、276,477 行 Python/TypeScript/Vue（其中 Python 约 175,254 行，前端约 101,223 行）、380 个 FastAPI 装饰器端点、229 个 Pydantic/端点模型、41 张 ORM 映射表；MySQL/PostgreSQL 最终迁移静态解析均覆盖约 47 张平台表。

## 2. 功能快速定位

| 功能 | 核心入口 | 记忆文件 | 主要数据 |
|---|---|---|---|
| 登录、SSO、API Key、RBAC | `/api/portal/auth/*`、`/management/*`、`/roles/*` | [02-auth-rbac-tenancy.md](docs/memory/02-auth-rbac-tenancy.md) | `ai_agent_users`、roles、relations、permissions |
| 对话、路由、AgentScope、SSE | `/api/v1/chat/*` | [03-chat-agent-runtime.md](docs/memory/03-chat-agent-runtime.md) | Redis conversation、execution history/traces |
| ChatBI、元数据、联邦查询 | `/api/v1/chatbi/*`、`/api/portal/metadata/*` | [04-chatbi-data.md](docs/memory/04-chatbi-data.md) | `meta_*`、DB connections、examples |
| 知识库、RAGFlow、长期记忆 | `/api/portal/ragflow/*`、`/memory/*` | [05-knowledge-memory.md](docs/memory/05-knowledge-memory.md) | knowledge metadata/metrics、Redis LTM |
| MCP、Skills、工具、文件与代码 | `/mcp/*`、`/skills/*`、`/api/v1/chat/fs/*` | [06-tools-integrations.md](docs/memory/06-tools-integrations.md) | MCP、tools、skill publications、workspace |
| 定时任务、报表、通知、工作台 | `/api/v1/tasks/*`、`/saved-reports/*` | [06-tasks-reports-notifications.md](docs/memory/06-tasks-reports-notifications.md) | tasks、saved reports、notifications |
| 前端路由与 API 映射 | `/dashboard/*`、`/embed/chat` | [07-frontend-experience.md](docs/memory/07-frontend-experience.md) | local state + 后端 API |
| 数据库与迁移 | `db-prod/`、`db-prod-pg/` | [08-operations-and-high-availability.md](docs/memory/08-operations-and-high-availability.md) | 全部平台表 |
| 安全风险与整改 | 全平台 | [02-auth-rbac-security.md](docs/memory/02-auth-rbac-security.md)、[risk-register.md](docs/memory/appendix/risk-register.md) | 身份、数据、密钥、工具边界 |
| 部署、可观测、HA、灾备 | `/live`、`/startup`、`/ready`、Docker、scheduler | [08-operations-and-high-availability.md](docs/memory/08-operations-and-high-availability.md) | DB、Redis、文件、任务执行 |

## 3. 路径前缀快速定位

| URL 前缀 | 模块 | 文档 |
|---|---|---|
| `/api/portal/auth`、`/management`、`/roles`、`/keys` | 身份与权限 | `02-auth-rbac-tenancy.md` |
| `/api/portal/agents`、`/prompts`、`/models` | Agent 生命周期 | `03-chat-agent-runtime.md` |
| `/api/v1/chat` | 对话、会话、SSE、文件与代码 | `03`、`06` |
| `/api/v1/chatbi`、`/api/v1/schema` | ChatBI 执行 | `04-chatbi-data.md` |
| `/api/portal/metadata`、`/data-portal` | 数据资产与数据门户 | `04-chatbi-data.md` |
| `/api/portal/ragflow`、`/memory` | 知识与记忆 | `05-knowledge-memory.md` |
| `/api/portal/mcp`、`/tools`、`/skills` | 扩展工具生态 | `06-tools-integrations.md` |
| `/api/v1/tasks`、`/saved-reports`、`/notifications`、`/inbox` | 异步任务与交付 | `06-tasks-reports-notifications.md` |
| `/api/portal/audit`、`/dashboard`、`/system`、`/quota` | 平台治理 | `02-auth-rbac-security.md`、`08-operations-and-high-availability.md` |

## 4. 核心业务链路

```text
登录 -> API Key/会话认证 -> 用户与角色权限聚合 -> 菜单/元素/资源/API 权限

用户提问 -> POST /api/v1/chat/completions -> Redis 会话锁与历史
        -> AgentContextManager -> RouterService -> Agent 权限复核
        -> Dispatcher -> Assistant / ChatBI / Knowledge / RAGFlow / OpenClaw
        -> AgentScope 工具循环 -> SSE content/log/citation -> 审计与会话持久化

自然语言查数 -> 授权数据集 Schema -> Text-to-SQL -> AST/表/列/行权限门禁
            -> 单源或联邦执行 -> 结果栈 -> 图表/简报/报表订阅

知识文档 -> RAGFlow/本地索引 -> 授权检索 -> 引用注入 -> 回答 -> 反馈/召回指标

场景模板 -> 资源绑定 -> 预检 -> Agent/版本安装 -> 验收问题 -> 交付清单

定时任务/报表订阅 -> Scheduler -> 模拟任务所有者身份 -> Agent 执行
                  -> 执行历史 -> Portal/钉钉/企微通知
```

## 5. 数据库快速索引

| 领域 | 表 |
|---|---|
| 身份权限 | `ai_agent_users`、`ai_agent_roles`、`ai_agent_user_role_relations`、`ai_agent_resource_permissions` |
| Agent 与模型 | `ai_agents`、`ai_agent_versions`、`ai_models`、`sys_api_tools` |
| 审计与额度 | `ai_agent_execution_history`、`ai_agent_execution_traces`、`ai_agent_access_logs`、`ai_agent_quota_policies` |
| ChatBI 元数据 | `meta_datasets`、`meta_tables`、`meta_columns`、`meta_metrics`、`meta_relationships`、`meta_db_connection_configs` |
| 数据分析 | `ai_chatbi_examples`、`ai_chatbi_example_usages`、`chatbi_briefs`、profile/changelog 表 |
| 知识与扩展 | `knowledge_base_metadata`、`knowledge_base_metrics`、`sys_mcp_servers`、`sys_mcp_tool_cache`、skill publication 表 |
| 任务与交付 | `ai_agent_scheduled_tasks`、`portal_saved_report*`、`portal_notifications`、`user_notification_configs` |
| 场景 | `ai_agent_scenario_instances`、`ai_agent_scenario_install_runs` |

字段、类型和源码映射见 [database-model-inventory.md](docs/memory/appendix/database-model-inventory.md)。物理 DDL 以 `db-prod/` 和 `db-prod-pg/` 为准。

## 6. 外部依赖快速索引

| 服务 | 目的 | 核心配置/位置 |
|---|---|---|
| OpenAI-compatible LLM / Embedding | 路由、执行、向量 | `LLM_*`、模型注册表、`embed_*` |
| RAGFlow | 知识库、检索、托管 Agent | `ragflow_*`、`knowledge_ragflow_*` |
| OpenClaw | 外部 Agent 网关 | `openclaw_*`、Agent `engine_config` |
| MCP Server | 动态工具发现与执行 | `sys_mcp_servers` |
| 企业 SSO | 登录与用户同步 | `SSO_*` |
| 外部 SQL/业务数据库 | ChatBI 查询 | `EXTERNAL_SQL_*`、DB connection config |
| Jira、钉钉、企业微信 | 工单与通知 | 环境变量/用户通知配置 |

详见 [external-apis.md](docs/memory/appendix/external-apis.md)、[config-reference.md](docs/memory/appendix/config-reference.md) 和 [config-key-inventory.md](docs/memory/appendix/config-key-inventory.md)。

## 7. 前端客户端快速索引

| 客户端 | 主要后端 |
|---|---|
| `frontend/src/api/agent.ts` | Agents、versions、history、logs |
| `frontend/src/api/metadata.ts` | datasets、tables、metrics、relationships、profiling、schema |
| `frontend/src/api/model.ts` | 模型 CRUD、发现和连通性测试 |
| `frontend/src/api/ragflow.ts` | RAGFlow agents、datasets、config |
| `frontend/src/api/task.ts` | tasks、logs、execution history、subscriptions |
| `frontend/src/api/portal.ts` | roles、users、scenario templates |
| `frontend/src/api/tool.ts` | API tools |
| `EmbedChat.vue` / `AgentDebug.vue` 内联 transport | chat SSE、资源范围、文件、代码执行、工具批准 |

## 8. 审计结论摘要

项目功能宽度和领域深度已经超过典型开源原型，尤其 ChatBI 权限链、知识引用、个人工作台、场景安装和多引擎分发具备产品差异化。但它尚未达到可直接承载多租户生产流量的“企业级”标准：代码执行缺少 OS 沙箱、ChatBI 直连 SQL 存在权限绕过、Markdown/Embed 存在浏览器安全漏洞、MCP 存在凭据泄露与 SSRF、凭据和会话模型不成熟；运维上仍是单实例、单 Redis、进程内调度和无版本账本迁移，缺少 CI、SLO、备份恢复与故障演练。

整改顺序必须是：**先封闭 P0 安全与数据越权 -> 再拆分状态/调度并建立可恢复性 -> 再做工程治理和产品 IA -> 最后扩展评测、工作流、市场与真正多租户。**

## 9. 维护规则

- 新增或修改端点：同步模块文档及 `appendix/endpoint-inventory.md`。
- 新增请求/响应字段：同步 `appendix/api-schema-inventory.md`。
- 新增 DB 列或索引：同时更新 MySQL、PostgreSQL 迁移、数据库 inventory 和 `08-operations-and-high-availability.md`。
- 新增外部 API 或配置键：更新 `appendix/external-apis.md` / `config-key-inventory.md`。
- 安全边界变更：更新 `02-auth-rbac-security.md`、风险清单并添加回归测试。
- 部署拓扑、SLO 或恢复策略变更：更新 `08-operations-and-high-availability.md`。
- 每次发布将本页审计基线更新为实际 commit；`PROJECT_MEMORY.md` 始终保持单一入口。
